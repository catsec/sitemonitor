# Site Monitor

A robust Python-based website monitoring service that watches for specific content patterns on websites and sends push notifications when found. Supports monitoring multiple URLs for multiple search terms simultaneously with intelligent duplicate prevention.

## Features

- **Multi-Site Monitoring**: Monitor multiple websites simultaneously
- **Multi-Term Search**: Search for multiple content patterns per site
- **Smart Text Matching**: Intelligent text normalization handles various formats
- **Duplicate Prevention**: Never sends the same notification twice
- **Parallel Processing**: Concurrent URL checking for optimal performance
- **Push Notifications**: Real-time alerts via Pushover API
- **Docker Ready**: Containerized deployment with health checks
- **Security First**: URL validation with SSRF protection
- **Resource Limits**: Built-in memory and content size protections

## Quick Start

### Prerequisites

- Docker and Docker Compose
- Pushover account ([sign up here](https://pushover.net/))

### Installation

1. Clone this repository
2. Create your Pushover application and get your tokens
3. Configure environment variables in `docker-compose.yml`
4. Run the service

```bash
# Clone and enter directory
git clone github.com/catsec/sitemonitor
cd sitemonitor

# Edit docker-compose.yml with your settings
nano docker-compose.yml

# Start the service
docker-compose up -d --build

# View logs
docker-compose logs -f
```

## Configuration

### Required Environment Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `PUSHOVER_TOKEN` | Your Pushover application token | `abcdef123456...` |
| `PUSHOVER_USER` | Your Pushover user key | `uvwxyz789012...` |
| `MONITOR_URL` | Website(s) to monitor (comma-separated) | `https://store1.com,https://store2.com` |
| `SEARCH_TEXT` | Search term(s) to find (comma-separated) | `iPhone 15,PlayStation 5` |

### Optional Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `CHECK_INTERVAL` | `300` | Check frequency in seconds |
| `NOTIFICATION_TITLE` | `Content Found!` | Custom notification title |
| `NOTIFICATION_PRIORITY` | `1` | Pushover priority (0-2) |
| `NOTIFICATION_SOUND` | `magic` | Pushover notification sound |
| `AUTO_STOP_ON_FOUND` | `true` | Stop after finding all items |
| `USER_AGENT` | Browser string | Custom browser user agent |
| `CUSTOM_HEADERS` | None | Additional HTTP headers (JSON) |
| `DEBUG` | `false` | Enable debug logging |

## Usage Examples

### Monitor Single Site for One Product

```yaml
environment:
  - MONITOR_URL=https://store.com/products/
  - SEARCH_TEXT=iPhone 15 Pro
```

### Monitor Multiple Sites for Multiple Products

```yaml
environment:
  - MONITOR_URL=https://store1.com,https://store2.com,https://store3.com
  - SEARCH_TEXT=iPhone 15 Pro,PlayStation 5,RTX 4090
```

This creates a 3×3 = 9 combination matrix. The service will:
- Send individual notifications as each combination is found
- Track progress (e.g., "Found 5/9 combinations")
- Continue until all combinations are found
- Send final completion summary

### Custom Notification Settings

```yaml
environment:
  - NOTIFICATION_TITLE=Product Alert!
  - NOTIFICATION_PRIORITY=2
  - NOTIFICATION_SOUND=siren
  - AUTO_STOP_ON_FOUND=false  # Keep monitoring even after finding items
```

### Advanced HTTP Configuration

```yaml
environment:
  - USER_AGENT=MyBot/1.0
  - CUSTOM_HEADERS={"Authorization": "Bearer token", "X-API-Key": "12345"}
```

## How It Works

### Smart Text Matching

The service uses intelligent text normalization that:
- Converts text to lowercase
- Removes punctuation and extra spaces
- Handles various formats (e.g., "iPhone-15-Pro" matches "iphone 15 pro")
- No complex regex knowledge required

### Comprehensive Content Analysis

Searches across all page content including:
- Visible page text
- Meta tags and page titles
- Image alt text and titles
- Link text and URLs
- Data attributes
- Form elements

### Duplicate Prevention

- Tracks every URL + search term combination
- Prevents sending the same notification multiple times
- Thread-safe for concurrent processing
- Automatic retry if notification sending fails

## Monitoring and Logs

### View Live Logs

```bash
docker-compose logs -f
```

### Check Service Status

```bash
docker-compose ps
```

### Monitor Resource Usage

```bash
docker stats sitemonitor
```

## Security Features

- **SSRF Protection**: Blocks private network access
- **Input Validation**: Sanitizes all user inputs
- **Size Limits**: Prevents memory exhaustion
- **Safe Parsing**: Validates JSON headers
- **Non-Root Execution**: Container runs as unprivileged user

## Troubleshooting

### Service Won't Start

1. Check your Pushover credentials are correct
2. Verify URLs are accessible and valid
3. Check logs: `docker-compose logs`

### No Notifications Received

1. Test Pushover credentials manually
2. Enable debug logging: `DEBUG=true`
3. Check if search terms exist on target pages
4. Verify notification settings

### High Memory Usage

1. Reduce number of monitored URLs
2. Increase check interval
3. Monitor large sites less frequently

### Common Error Messages

| Error | Solution |
|-------|----------|
| `Invalid or unsafe URL` | Check URL format and accessibility |
| `Configuration validation failed` | Verify required environment variables |
| `Failed to fetch page` | Check network connectivity and URL validity |
| `PUSHOVER_TOKEN environment variable is required` | Set Pushover credentials |

## Development

### Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables
export PUSHOVER_TOKEN=your_token
export PUSHOVER_USER=your_user
export MONITOR_URL=https://example.com
export SEARCH_TEXT="Product Name"

# Run directly
python monitor.py
```

### Project Structure

```
sitemonitor/
├── monitor.py          # Main application
├── requirements.txt    # Python dependencies
├── Dockerfile         # Container definition
├── docker-compose.yml # Service configuration
├── CLAUDE.md          # Development guidance
└── README.md          # This file
```

## Resource Requirements

- **Memory**: 256MB (configurable)
- **CPU**: Minimal usage
- **Network**: Outbound HTTPS access required
- **Storage**: ~100MB for logs

## License

This project is provided as-is for monitoring publicly accessible websites. Please respect robots.txt and website terms of service when using this tool.

## Support

For issues and questions:
1. Check the troubleshooting section above
2. Review logs with `DEBUG=true`
3. Verify configuration against examples

4. Test with simple single-site setup first
