FROM python:3.11-slim

# Prevent Python from buffering stdout and stderr
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Install system utilities needed for building packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies first to leverage Docker layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy source code and static assets
COPY config.py parsers.py tenant_store.py main.py ./
COPY static ./static

# Ensure db directory exists
RUN mkdir -p /app/db

EXPOSE 8000

# Run with 2 worker processes for concurrency on free-tier CPU constraints
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]