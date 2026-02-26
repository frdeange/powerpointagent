FROM python:3.13-slim

WORKDIR /app

# Install system dependencies for python-pptx / Pillow
RUN apt-get update && apt-get install -y --no-install-recommends \
    libxml2 \
    libxslt1.1 \
    libjpeg-dev \
    libpng-dev \
    zlib1g \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

ENV PORT=8000

# FastMCP stateless_http runs via uvicorn internally
CMD ["python", "server.py"]
