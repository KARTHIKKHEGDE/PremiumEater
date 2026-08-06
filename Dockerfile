# Use the official Python image
FROM python:3.11-slim

# Prevent Python from buffering stdout and stderr
ENV PYTHONUNBUFFERED 1

# Install system dependencies required by Playwright (Chromium)
# These are lightweight and only ~30MB. Chromium itself is installed conditionally.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Chromium browser binary (optional — only needed if NSE_COOKIES env var is NOT set)
# Comment out the next line to save ~400MB if you always use NSE_COOKIES env var
RUN playwright install chromium || echo "Playwright install failed — will use NSE_COOKIES env var"

# Copy the rest of the application code
COPY . .

# Start the FastAPI application
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}
