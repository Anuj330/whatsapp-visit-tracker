FROM python:3.12-slim

WORKDIR /app

# Install dependencies first for better layer caching.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# Match Render's default web port so its port scan and EXPOSE agree.
EXPOSE 10000

# Render injects $PORT (10000 by default); fall back to it for local runs too.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-10000}"]
