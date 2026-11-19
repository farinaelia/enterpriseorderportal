# Enterprise Order Portal - container image
# Build:  docker build -t order-portal .
# Run:    docker run -p 8000:8000 -v portal-data:/data order-portal
FROM python:3.12-slim

# Do not write .pyc files, and print logs immediately.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORTAL_DATA_DIR=/data

WORKDIR /app

# Install dependencies first: Docker caches this layer until requirements change.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn

COPY . .

# Run as a normal user, not root. /data holds the database and uploads.
RUN useradd --create-home appuser && mkdir /data && chown appuser /data
USER appuser
VOLUME /data
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz')" || exit 1

# One worker with several threads: SQLite creates and seeds its file on first
# start, and several worker processes would race to do that.
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "1", "--threads", "4", "run:app"]
