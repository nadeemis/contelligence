FROM python:3.12-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Playwright browsers (for web scraping tool)
RUN pip install --no-cache-dir playwright && playwright install chromium --with-deps

# Install Python dependencies
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Phase 3 — install Azure MCP Server (stdio mode)
RUN pip install --no-cache-dir msmcp-azure && azmcp --version

# Copy application code
COPY . /app
WORKDIR /app

# Expose port
EXPOSE 8000

# Start FastAPI application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
