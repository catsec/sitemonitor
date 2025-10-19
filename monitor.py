#!/usr/bin/env python3
"""
Site Monitor
Monitors websites for specific content patterns
Sends Pushover notifications when found
"""

import os
import time
import sys
import requests
from bs4 import BeautifulSoup
import logging
from datetime import datetime
import json
from urllib.parse import urlparse, urljoin
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import re

# Configure logging
log_level = logging.DEBUG if os.getenv('DEBUG', 'false').lower() == 'true' else logging.INFO
logging.basicConfig(
    level=log_level,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/app/logs/monitor.log'),
        logging.StreamHandler()
    ]
)

class SiteMonitor:
    # Configuration constants
    MAX_CONTENT_SIZE = 1024 * 1024 * 20  # 20MB limit (increased for large e-commerce sites)
    MAX_URLS = 10  # Maximum URLs to prevent abuse
    MAX_SEARCH_TERMS = 20  # Maximum search terms
    REQUEST_TIMEOUT = 60  # Increased for slower sites
    RETRY_DELAY = 60
    MAX_RETRIES = 3
    MAX_WORKERS = 4  # Maximum concurrent threads
    TEXT_LIMIT = 100000  # 100K chars for text normalization (increased for large pages)
    NOTIFICATION_TEXT_LIMIT = 150  # Max chars in notification text
    PRODUCT_TEXT_LIMIT = 200  # Max chars for product container text

    def __init__(self):
        # Load URLs from environment or use default
        urls_env = os.getenv('MONITOR_URL')
        raw_urls = [url.strip() for url in urls_env.split(',') if url.strip()]

        # Validate URLs
        self.urls = []
        for url in raw_urls[:self.MAX_URLS]:  # Limit number of URLs
            if self._validate_url(url):
                self.urls.append(url)
            else:
                logging.warning(f"Invalid or unsafe URL ignored: {url}")

        if not self.urls:
            raise ValueError("No valid URLs provided")
        self.pushover_token = os.getenv('PUSHOVER_TOKEN')
        self.pushover_user = os.getenv('PUSHOVER_USER')
        self.check_interval = int(os.getenv('CHECK_INTERVAL', '300'))  # 5 minutes default
        self.user_agent = os.getenv('USER_AGENT', "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")

        # Notification settings
        self.notification_title = os.getenv('NOTIFICATION_TITLE', 'Content Found!')
        self.notification_priority = int(os.getenv('NOTIFICATION_PRIORITY', '1'))  # High priority by default
        self.notification_sound = os.getenv('NOTIFICATION_SOUND', 'magic')
        self.auto_stop_on_found = os.getenv('AUTO_STOP_ON_FOUND', 'true').lower() == 'true'

        # Default search text (can be overridden via environment variable)
        default_search_text = "DJI Mini 5 Pro"

        # Load search text from environment or use default
        search_text_env = os.getenv('SEARCH_TEXT')
        if search_text_env:
            # Split by comma and strip whitespace for multiple search terms
            raw_search_texts = [text.strip() for text in search_text_env.split(',') if text.strip()]
            self.search_texts = raw_search_texts[:self.MAX_SEARCH_TERMS]  # Limit search terms
        else:
            self.search_texts = [default_search_text]

        # Initialize tracking for found items to prevent duplicate notifications
        # Structure: {url: {search_term: found_timestamp}}
        self.found_items = {}
        self.notification_sent = {}  # Track sent notifications to prevent duplicates
        for url in self.urls:
            self.found_items[url] = {}
            self.notification_sent[url] = {}
            for search_text in self.search_texts:
                self.found_items[url][search_text] = None
                self.notification_sent[url][search_text] = False

        # Thread lock for concurrent access
        self._lock = threading.Lock()

        # Validate required configuration
        self._validate_config()

    def _validate_url(self, url):
        """Validate URL for security and format"""
        try:
            parsed = urlparse(url)

            # Must have scheme and netloc
            if not parsed.scheme or not parsed.netloc:
                return False

            # Only allow HTTP/HTTPS
            if parsed.scheme not in ['http', 'https']:
                return False

            # Block private/local networks (basic SSRF protection)
            hostname = parsed.hostname
            if hostname:
                # Block localhost, 127.x.x.x, 192.168.x.x, 10.x.x.x, 172.16-31.x.x
                if (hostname == 'localhost' or
                    hostname.startswith('127.') or
                    hostname.startswith('192.168.') or
                    hostname.startswith('10.') or
                    (hostname.startswith('172.') and
                     any(hostname.startswith(f'172.{i}.') for i in range(16, 32)))):
                    return False

            return True
        except Exception:
            return False

    def _normalize_text(self, text):
        """Normalize text for comparison by converting to lowercase and removing delimiters"""
        if not text:
            return ""

        # Limit text size to prevent memory issues
        text = str(text)[:self.TEXT_LIMIT]

        # Convert to lowercase
        text = text.lower()

        # Use regex for better performance
        # Replace non-alphanumeric chars with spaces, then collapse spaces
        normalized = re.sub(r'[^a-z0-9\s]', ' ', text)
        normalized = re.sub(r'\s+', ' ', normalized).strip()

        return normalized

    def _validate_config(self):
        """Validate configuration settings and provide helpful error messages"""
        errors = []

        if not self.pushover_token:
            errors.append("PUSHOVER_TOKEN environment variable is required")
        if not self.pushover_user:
            errors.append("PUSHOVER_USER environment variable is required")
        if not self.urls:
            errors.append("MONITOR_URL environment variable cannot be empty")
        if not self.search_texts:
            errors.append("SEARCH_TEXT cannot be empty")
        if self.check_interval < 10:
            errors.append("CHECK_INTERVAL must be at least 10 seconds")

        if errors:
            for error in errors:
                logging.error(error)
            raise ValueError(f"Configuration validation failed: {'; '.join(errors)}")

        logging.info(f"Configuration loaded successfully:")
        logging.info(f"  URLs: {self.urls}")
        logging.info(f"  Search texts: {self.search_texts}")
        logging.info(f"  Check interval: {self.check_interval} seconds")
        logging.info(f"  Auto-stop on found: {self.auto_stop_on_found}")
        logging.info(f"  Total combinations to find: {len(self.urls)} URLs × {len(self.search_texts)} terms = {len(self.urls) * len(self.search_texts)}")

    def send_pushover_notification(self, message, title=None):
        """Send notification via Pushover"""
        try:
            response = requests.post(
                "https://api.pushover.net/1/messages.json",
                data={
                    "token": self.pushover_token,
                    "user": self.pushover_user,
                    "title": title or self.notification_title,
                    "message": message,
                    "priority": self.notification_priority,
                    "sound": self.notification_sound
                },
                timeout=30
            )

            if response.status_code == 200:
                logging.info("Pushover notification sent successfully")
                return True
            else:
                logging.error(f"Failed to send Pushover notification: {response.status_code} - {response.text}")
                return False

        except Exception as e:
            logging.error(f"Error sending Pushover notification: {str(e)}")
            return False

    def fetch_page(self, url):
        """Fetch the specified page"""
        # Build headers - start with defaults and allow customization
        headers = {
            'User-Agent': self.user_agent,
            'Accept': os.getenv('HTTP_ACCEPT', 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8'),
            'Accept-Language': os.getenv('HTTP_ACCEPT_LANGUAGE', 'en-US,en;q=0.5'),
            'Accept-Encoding': os.getenv('HTTP_ACCEPT_ENCODING', 'gzip, deflate'),
            'Connection': os.getenv('HTTP_CONNECTION', 'keep-alive'),
            'Upgrade-Insecure-Requests': os.getenv('HTTP_UPGRADE_INSECURE', '1'),
        }

        # Allow additional custom headers via environment variable (JSON format)
        custom_headers = os.getenv('CUSTOM_HEADERS')
        if custom_headers:
            try:
                additional_headers = json.loads(custom_headers)
                # Validate headers are safe
                if isinstance(additional_headers, dict):
                    safe_headers = {}
                    for key, value in additional_headers.items():
                        if isinstance(key, str) and isinstance(value, str):
                            # Sanitize header names/values
                            key = key.strip()[:100]  # Limit length
                            value = value.strip()[:500]  # Limit length
                            if key and not any(c in key for c in ['\n', '\r', '\0']):
                                safe_headers[key] = value
                    headers.update(safe_headers)
                    logging.debug(f"Added custom headers: {list(safe_headers.keys())}")
                else:
                    logging.warning("CUSTOM_HEADERS must be a JSON object")
            except json.JSONDecodeError as e:
                logging.warning(f"Invalid JSON in CUSTOM_HEADERS, ignoring: {e}")

        for attempt in range(self.MAX_RETRIES):
            try:
                response = requests.get(url, headers=headers, timeout=self.REQUEST_TIMEOUT)
                response.raise_for_status()

                # Check content size
                content_length = len(response.content)
                if content_length > self.MAX_CONTENT_SIZE:
                    logging.warning(f"Content too large ({content_length} bytes), truncating")
                    return response.text[:self.MAX_CONTENT_SIZE//2]  # Rough text limit

                return response.text

            except requests.Timeout:
                logging.warning(f"Timeout fetching {url} (attempt {attempt + 1}/{self.MAX_RETRIES})")
            except requests.ConnectionError as e:
                logging.warning(f"Connection error fetching {url} (attempt {attempt + 1}/{self.MAX_RETRIES}): {e}")
            except requests.HTTPError as e:
                if e.response.status_code >= 500:
                    logging.warning(f"Server error {e.response.status_code} for {url} (attempt {attempt + 1}/{self.MAX_RETRIES})")
                else:
                    logging.error(f"HTTP error {e.response.status_code} for {url}: {e}")
                    return None  # Don't retry client errors
            except Exception as e:
                logging.error(f"Unexpected error fetching {url}: {e}")
                return None

            if attempt < self.MAX_RETRIES - 1:
                wait_time = (attempt + 1) * 5  # Exponential backoff: 5s, 10s, 15s
                logging.info(f"Retrying {url} in {wait_time} seconds...")
                time.sleep(wait_time)

        logging.error(f"Failed to fetch {url} after {self.MAX_RETRIES} attempts")
        return None

    def _collect_searchable_content(self, soup):
        """Extract all searchable content from parsed HTML"""
        searchable_content = []

        # 1. All visible text on the page
        page_text = soup.get_text()
        searchable_content.append(page_text)
        logging.debug(f"Added visible text: {len(page_text)} characters")

        # 2. Page title
        if soup.title and soup.title.string:
            searchable_content.append(soup.title.string)
            logging.debug(f"Added page title: {soup.title.string}")

        # 3. Meta descriptions and keywords
        for meta in soup.find_all('meta'):
            if meta.get('name') in ['description', 'keywords'] and meta.get('content'):
                searchable_content.append(meta['content'])
                logging.debug(f"Added meta {meta.get('name')}: {meta['content'][:50]}...")

        # 4. Image alt text and titles
        for img in soup.find_all('img'):
            if img.get('alt'):
                searchable_content.append(img['alt'])
            if img.get('title'):
                searchable_content.append(img['title'])

        # 5. Link titles and href content
        for link in soup.find_all('a'):
            if link.get('title'):
                searchable_content.append(link['title'])
            if link.get('href'):
                searchable_content.append(link['href'])

        # 6. Data attributes that might contain product info
        for element in soup.find_all(attrs={'data-product-name': True}):
            searchable_content.append(element.get('data-product-name'))
        for element in soup.find_all(attrs={'data-title': True}):
            searchable_content.append(element.get('data-title'))

        # 7. Form input values and placeholders
        for input_elem in soup.find_all(['input', 'textarea']):
            if input_elem.get('placeholder'):
                searchable_content.append(input_elem['placeholder'])
            if input_elem.get('value'):
                searchable_content.append(input_elem['value'])

        return searchable_content

    def _extract_product_details(self, soup, found_texts, url):
        """Extract detailed product information for found items"""
        product_info = []

        for search_text in found_texts:
            # Search in links
            for link in soup.find_all('a'):
                link_text = link.get_text().strip()
                if (search_text.lower() in link_text.lower() or
                    self._normalize_text(search_text) in self._normalize_text(link_text)):
                    href = link.get('href')
                    full_url = urljoin(url, href) if href else None
                    product_info.append({
                        'type': 'link',
                        'text': link_text,
                        'url': href,
                        'full_url': full_url,
                        'search_term': search_text,
                        'found_at': url
                    })
                    break

            # Search in headings
            for heading in soup.find_all(['h1', 'h2', 'h3', 'h4']):
                heading_text = heading.get_text().strip()
                if (search_text.lower() in heading_text.lower() or
                    self._normalize_text(search_text) in self._normalize_text(heading_text)):
                    product_info.append({
                        'type': 'heading',
                        'text': heading_text,
                        'url': None,
                        'tag': heading.name,
                        'search_term': search_text,
                        'found_at': url
                    })
                    break

            # Search in product containers
            for container in soup.find_all(['div', 'article', 'section'],
                                         class_=lambda x: x and 'product' in str(x).lower()):
                container_text = container.get_text()
                if self._normalize_text(search_text) in self._normalize_text(container_text):
                    # Find price and link
                    price_elem = container.find(string=lambda text: text and
                                              any(char in str(text) for char in ['₪', '$', '€', '£']) and
                                              any(char.isdigit() for char in str(text)))
                    link_elem = container.find('a')

                    product_info.append({
                        'type': 'product_container',
                        'text': (container_text.strip()[:self.PRODUCT_TEXT_LIMIT] + '...'
                                if len(container_text) > self.PRODUCT_TEXT_LIMIT else container_text.strip()),
                        'price': str(price_elem).strip() if price_elem else 'Price not found',
                        'url': link_elem.get('href') if link_elem else None,
                        'search_term': search_text,
                        'found_at': url
                    })
                    break

        return product_info

    def check_for_patterns(self, html_content, url, specific_search_texts=None):
        """Check if search text is found on the page - COMPREHENSIVE SEARCH"""
        if not html_content:
            return False, None

        soup = BeautifulSoup(html_content, 'html.parser')

        # Collect all searchable content
        searchable_content = self._collect_searchable_content(soup)

        # Combine and normalize content
        all_content = ' '.join(str(content) for content in searchable_content if content)
        normalized_content = self._normalize_text(all_content)

        logging.info(f"Comprehensive search: scanning {len(normalized_content)} normalized characters")

        # Determine which search texts to check
        search_texts_to_check = specific_search_texts or self.search_texts

        # Find matching texts
        found_texts = []
        found_locations = []

        for search_text in search_texts_to_check:
            # Thread-safe check for already found items
            with self._lock:
                if self.found_items[url].get(search_text):
                    continue

            normalized_search = self._normalize_text(search_text)
            if normalized_search in normalized_content:
                # Thread-safe update
                with self._lock:
                    if not self.found_items[url].get(search_text):  # Double-check
                        found_texts.append(search_text)
                        found_locations.append(f"Text '{search_text}' found at {url}")
                        self.found_items[url][search_text] = datetime.now()

        if found_texts:
            logging.info(f"FOUND TEXTS: {found_locations}")
            product_info = self._extract_product_details(soup, found_texts, url)
            return True, product_info

        logging.info("Search texts not found in comprehensive search")
        return False, None

    def _check_single_url(self, url):
        """Check a single URL for patterns - used for parallel processing"""
        logging.info(f"Checking URL: {url}")

        html_content = self.fetch_page(url)
        if not html_content:
            logging.warning(f"Failed to fetch page content for {url}")
            return []

        found, product_info = self.check_for_patterns(html_content, url)

        if found and product_info:
            return product_info
        return []

    def run_check(self):
        """Run a single check across all URLs and search terms - with parallel processing"""
        logging.info("Starting parallel check for content patterns across all URLs...")

        any_new_found = False
        all_product_info = []

        # Use ThreadPoolExecutor for parallel URL processing
        max_workers = min(len(self.urls), self.MAX_WORKERS)  # Limit concurrent connections
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all URL checks
            future_to_url = {executor.submit(self._check_single_url, url): url for url in self.urls}

            # Collect results as they complete
            for future in as_completed(future_to_url):
                url = future_to_url[future]
                try:
                    product_info = future.result()
                    if product_info:
                        any_new_found = True
                        all_product_info.extend(product_info)

                        # Send individual notifications for each newly found item
                        for info in product_info:
                            search_term = info.get('search_term', 'Unknown')
                            found_at = info.get('found_at', url)

                            # Double-check notification wasn't already sent (thread safety)
                            with self._lock:
                                if self.notification_sent[found_at][search_term]:
                                    continue
                                self.notification_sent[found_at][search_term] = True

                            message = f"'{search_term}' FOUND!\n\n"
                            message += f"Site: {found_at}\n\n"
                            message += f"Type: {info.get('type', 'unknown')}\n"
                            message += f"Text: {info['text'][:self.NOTIFICATION_TEXT_LIMIT]}{'...' if len(info['text']) > self.NOTIFICATION_TEXT_LIMIT else ''}\n"

                            if info.get('full_url'):
                                message += f"Link: {info['full_url']}\n"

                            if info.get('price') and info['price'] != 'Price not found':
                                message += f"Price: {info['price']}\n"

                            message += f"\nCheck immediately: {found_at}"

                            # Send notification for this specific find
                            success = self.send_pushover_notification(message, f"Found: {search_term}")
                            if not success:
                                # Reset flag if notification failed
                                with self._lock:
                                    self.notification_sent[found_at][search_term] = False

                except Exception as e:
                    logging.error(f"Error processing results for {url}: {e}")

        return any_new_found

    def get_completion_status(self):
        """Check how many items have been found vs total expected"""
        total_expected = len(self.urls) * len(self.search_texts)
        found_count = 0

        for url in self.urls:
            for search_text in self.search_texts:
                if self.found_items[url].get(search_text):
                    found_count += 1

        return found_count, total_expected

    def all_items_found(self):
        """Check if all search terms have been found in all URLs"""
        found_count, total_expected = self.get_completion_status()
        return found_count == total_expected

    def start_monitoring(self):
        """Start continuous monitoring"""
        logging.info(f"Starting site monitor - checking every {self.check_interval} seconds")

        # Send startup notification
        url_list = "\n".join([f"- {url}" for url in self.urls])
        search_list = "\n".join([f"- {text}" for text in self.search_texts])

        startup_message = f"Site Monitor started successfully!\n\n"
        startup_message += f"Monitoring {len(self.urls)} URL(s):\n{url_list}\n\n"
        startup_message += f"Searching for {len(self.search_texts)} term(s):\n{search_list}\n\n"
        startup_message += f"Check interval: {self.check_interval//60} minutes\n"
        startup_message += f"Total combinations to find: {len(self.urls) * len(self.search_texts)}"

        self.send_pushover_notification(startup_message, "Site Monitor Started")

        while True:
            try:
                found = self.run_check()

                # Check if all items have been found
                found_count, total_expected = self.get_completion_status()
                logging.info(f"Progress: {found_count}/{total_expected} combinations found")

                if self.all_items_found() and self.auto_stop_on_found:
                    logging.info("ALL ITEMS FOUND! Mission accomplished - stopping monitor.")

                    # Send final notification
                    final_message = "Site Monitor has completed its mission successfully!\n\n"
                    final_message += f"All {total_expected} search combinations have been found:\n\n"

                    for url in self.urls:
                        final_message += f"Site: {url}:\n"
                        for search_text in self.search_texts:
                            if self.found_items[url][search_text]:
                                timestamp = self.found_items[url][search_text].strftime("%Y-%m-%d %H:%M:%S")
                                final_message += f"  [FOUND] {search_text} (found at {timestamp})\n"
                            else:
                                final_message += f"  [NOT FOUND] {search_text}\n"
                        final_message += "\n"

                    final_message += "The monitor will now stop to avoid spam notifications."

                    self.send_pushover_notification(final_message, "Mission Complete - All Items Found!")

                    logging.info("Monitor stopped successfully after finding all items")
                    sys.exit(0)  # Clean exit - mission accomplished!

                elif found:
                    logging.info(f"NEW ITEMS FOUND! Progress: {found_count}/{total_expected}. Continuing to monitor.")

                if found_count > 0:
                    logging.info(f"Still searching for {total_expected - found_count} more combinations...")

                logging.info(f"Next check in {self.check_interval} seconds...")
                time.sleep(self.check_interval)

            except KeyboardInterrupt:
                logging.info("Monitor stopped by user")
                break
            except Exception as e:
                logging.error(f"Unexpected error: {str(e)}")
                time.sleep(60)  # Wait 1 minute before retrying on error

        logging.info("Site Monitor has finished execution")

if __name__ == "__main__":
    try:
        monitor = SiteMonitor()
        monitor.start_monitoring()
    except Exception as e:
        logging.error(f"Failed to start monitor: {str(e)}")