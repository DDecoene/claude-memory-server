# Multi-arch image — works on Raspberry Pi (arm/v7 and arm64) and x86_64
FROM python:3.11-slim

WORKDIR /app

# Install deps first (cached layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY server.py .

# /data is where the SQLite database lives — mount the USB SSD here
RUN mkdir -p /data

EXPOSE 8765

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8765", "--workers", "1"]
