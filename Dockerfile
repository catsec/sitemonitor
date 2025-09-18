FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better layer caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Create logs directory
RUN mkdir -p /app/logs

# Copy application code
COPY monitor.py .

# Make the script executable
RUN chmod +x monitor.py

# Create non-root user for security
RUN useradd --create-home --shell /bin/bash app && chown -R app:app /app
USER app

# Health check
HEALTHCHECK --interval=5m --timeout=30s --start-period=1m --retries=3 \
    CMD python -c "import os; print('Monitor running')" || exit 1

# Run the monitor
CMD ["python", "monitor.py"]