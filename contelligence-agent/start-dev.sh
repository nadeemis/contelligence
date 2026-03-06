#!/bin/bash
set -e

# Contelligence Agent — Local Development Startup Script
# Usage: ./start-dev.sh

cd "$(dirname "$0")"

# Check for .env file
if [ ! -f .env ]; then
    echo "Warning: .env file not found. Copy .env.example to .env and configure it."
    echo "  cp .env.example .env"
fi

# Start FastAPI with hot-reload
echo "Starting Contelligence Agent on http://localhost:8000 ..."
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
