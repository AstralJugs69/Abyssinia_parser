---
description: Repository Information Overview
alwaysApply: true
---

# Bank Document Parser Information

## Summary
A Django web application for parsing and digitizing bank documents using OCR and LLM technology. The application processes bank-related tables from images or PDFs, extracts text using Tesseract OCR, and structures the data using Google's Gemini AI. The processed data can be exported to Excel or embedded-text PDF formats.

## Structure
- **document_parser/**: Django project configuration files
- **parser/**: Main Django application with models, views, and services
- **parser/templates/**: HTML templates for the web interface
- **parser/static/**: Static assets (CSS, JS, images)
- **parser/management/**: Custom Django management commands

## Language & Runtime
**Language**: Python
**Version**: Python 3.10+ (3.11 in Docker)
**Framework**: Django 5.2.5
**Build System**: pip
**Package Manager**: pip

## Dependencies
**Main Dependencies**:
- Django 5.2.5: Web framework
- pytesseract 0.3.13: OCR engine wrapper
- google-generativeai 0.8.3: Gemini AI integration
- openpyxl 3.1.5: Excel file generation
- PyMuPDF 1.24.10: PDF processing
- Pillow 10.4.0: Image processing
- reportlab 4.2.2: PDF generation

**Development Dependencies**:
- pytest: Testing framework

## Build & Installation
```bash
pip install -r requirements.txt
python manage.py runserver
```

## Docker
**Dockerfile**: Dockerfile
**Image**: Python 3.11-slim with Tesseract OCR
**Configuration**: 
- Installs Tesseract OCR with Amharic language support
- Uses Gunicorn as the WSGI server
- Exposes port 8000 (configurable via PORT env var)
- Configured for Railway deployment

**Docker Compose**:
```bash
docker-compose up
```

## Testing
**Framework**: pytest with Django test support
**Test Location**: parser/tests.py
**Configuration**: pytest.ini
**Run Command**:
```bash
pytest
```

## Environment Configuration
**Required Variables**:
- SECRET_KEY: Django secret key
- GEMINI_API_KEY: Google Generative AI API key

**Optional Variables**:
- GEMINI_MODEL: AI model to use (default: gemini-2.5-pro)
- GEMINI_USE_VISION: Enable direct image analysis
- TESSERACT_PSM, TESSERACT_OEM, TESSERACT_LANG: OCR tuning