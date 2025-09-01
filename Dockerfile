# Railway deployment: Python + Tesseract + Django
FROM python:3.11-slim

# Prevent Python from writing .pyc files and buffering stdout
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# System dependencies
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       tesseract-ocr \
       tesseract-ocr-amh \
       libtesseract-dev \
       libleptonica-dev \
       build-essential \
       libjpeg-dev \
       zlib1g-dev \
       libpng-dev \
       fonts-dejavu-core \
       fonts-sil-abyssinica \
    && rm -rf /var/lib/apt/lists/*

# Workdir
WORKDIR /app

# Install Python dependencies first (better caching)
COPY requirements.txt requirements.deploy.txt /app/
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt -r requirements.deploy.txt

# Copy project
COPY . /app

# Collect static (no-op if none)
RUN python manage.py collectstatic --noinput || true

EXPOSE 8000

# Gunicorn entrypoint (bind to $PORT on Railway, fallback to 8000 locally)
CMD ["/bin/sh", "-c", "gunicorn document_parser.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers 2 --threads 4 --timeout 120"]
