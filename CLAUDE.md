# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Python-based website monitoring service that watches for specific content on websites. It sends push notifications via Pushover when the specified content is detected and runs as a containerized service. The service supports monitoring multiple URLs for multiple search terms simultaneously.

## Core Architecture

- **Single Python Application**: `monitor.py` contains the main monitoring logic
- **Web Scraping**: Uses `requests` and `BeautifulSoup` for comprehensive content analysis
- **Notification Service**: Integrates with Pushover API for real-time alerts
- **Containerized Deployment**: Designed to run in Docker with health checks and resource limits
- **Parallel Processing**: Uses ThreadPoolExecutor for concurrent URL monitoring
- **Duplicate Prevention**: Tracks found items to prevent notification spam

## Development Commands

### Running the Application

**Docker (Recommended):**
```bash
# Build and run with docker-compose
docker-compose up --build

# Run in background
docker-compose up -d --build

# View logs
docker-compose logs -f

# Stop the service
docker-compose down
```

**Direct Python execution:**
```bash
# Install dependencies
pip install -r requirements.txt

# Set required environment variables
export PUSHOVER_TOKEN=your_token
export PUSHOVER_USER=your_user
export MONITOR_URL=https://example.com/shop/
export SEARCH_TEXT="Product Name,Another Product"

# Run the monitor
python monitor.py
```

### Configuration

**Required environment variables:**
- `PUSHOVER_TOKEN`: Pushover application token
- `PUSHOVER_USER`: Pushover user key
- `MONITOR_URL`: Website(s) to monitor (comma-separated for multiple)
- `SEARCH_TEXT`: Search term(s) to look for (comma-separated for multiple)

**Optional environment variables:**
- `CHECK_INTERVAL`: Check frequency in seconds (default: 300)
- `NOTIFICATION_TITLE`: Custom notification title (default: "Content Found!")
- `NOTIFICATION_PRIORITY`: Pushover priority 0-2 (default: 1)
- `NOTIFICATION_SOUND`: Pushover notification sound (default: "magic")
- `AUTO_STOP_ON_FOUND`: Stop after finding all items (default: true)
- `USER_AGENT`: Custom browser user agent
- `CUSTOM_HEADERS`: Additional HTTP headers in JSON format
- `DEBUG`: Enable debug logging (default: false)
- `TZ`: Timezone setting

## Key Components

### SiteMonitor Class (`monitor.py:33`)
- Main monitoring logic with comprehensive web scraping
- Configurable search text for content detection
- Health check and error handling mechanisms
- Automatic shutdown after successful content detection (optional)
- Multi-URL and multi-term support with duplicate prevention

### Search Strategy
The monitor performs comprehensive content analysis including:
- Visible page text and meta tags
- Image alt text and link titles
- Data attributes and form elements
- URL content analysis
- Smart text normalization (removes punctuation, handles spacing)

### Notification System
- Configurable Pushover notifications
- Individual notifications for each found item
- Detailed content information including links and prices
- Startup and completion notifications
- Progress tracking for multiple search combinations

## Container Configuration

- **Base Image**: `python:3.11-slim`
- **Memory Limit**: 256MB (configurable)
- **Health Check**: 5-minute intervals
- **Security**: Runs as non-root user
- **Persistence**: Logs stored in `./logs` volume
- **Content Limits**: 20MB max page size, 100K text processing

## Search Functionality

The monitor uses simple text matching with smart normalization:
- Converts text to lowercase
- Removes punctuation and extra spaces
- Handles various text formats (e.g., "Product-Name" matches "product name")
- No complex regex patterns required

**Example search terms:**
- `iPhone 15 Pro`
- `PlayStation 5`
- `RTX 4090`

## Multi-Site Monitoring

The service supports monitoring multiple websites for multiple products:
- Each URL + search term combination is tracked independently
- Prevents duplicate notifications for the same item
- Parallel processing for faster checks
- Comprehensive progress tracking
- Optional auto-stop when all combinations found

## Security Features

- URL validation with SSRF protection
- Blocks private network access
- Input sanitization and size limits
- Safe JSON header parsing
- Request timeout and retry logic
- Content size limits to prevent memory exhaustion