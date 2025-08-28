# Bank Document Parser

A Django web application for parsing and digitizing bank documents using OCR and LLM technology.

## Setup Instructions

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Environment Configuration
1. Copy `.env.example` to `.env`
2. Fill in your Supabase and OpenAI credentials:
   - `SUPABASE_URL`: Your Supabase project URL
   - `SUPABASE_KEY`: Your Supabase anon key
   - `SUPABASE_DB_HOST`: Your Supabase database host
   - `SUPABASE_DB_PASSWORD`: Your Supabase database password
   - `OPENAI_API_KEY`: Your OpenAI API key

### 3. Database Setup
```bash
python manage.py makemigrations
python manage.py migrate
```

### 4. Run Development Server
```bash
python manage.py runserver
```

## Features
- Upload and process images (JPG, PNG, PDF) and text files
- OCR text extraction using Tesseract
- LLM-powered data structuring using OpenAI
- Export to Excel, PDF, and DOC formats
- Support for up to 4 concurrent users
- Automatic file cleanup after 1 hour

## Requirements
- Python 3.8+
- Tesseract OCR installed on system
- Supabase account and database
- OpenAI API key