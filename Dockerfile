# Railway deployment: Python + Tesseract + Django
FROM python:3.11-slim

# Prevent Python from writing .pyc files and buffering stdout
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# System dependencies for OCR and image processing
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       tesseract-ocr \
       tesseract-ocr-eng \
       tesseract-ocr-amh \
       libtesseract-dev \
       libjpeg62-turbo \
       zlib1g \
       libpng16-16 \
       libfreetype6-dev \
       fonts-sil-abyssinica \
       poppler-utils \
    && rm -rf /var/lib/apt/lists/*

# Workdir
WORKDIR /app

# Install Python dependencies first (better caching)
COPY requirements.txt requirements.deploy.txt /app/
RUN pip install --no-cache-dir --upgrade pip \
    && pip install -r requirements.txt -r requirements.deploy.txt

# Copy project
COPY . /app

# Collect static during build to warm cache (non-fatal if settings not ready)
RUN python manage.py collectstatic --noinput || true

EXPOSE 8000

# Run migrations then start Gunicorn (bind to $PORT on Railway, fallback to 8000 locally)
CMD ["/bin/sh", "-c", "python manage.py migrate --noinput && gunicorn document_parser.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers 2 --threads 4 --timeout 120"]
