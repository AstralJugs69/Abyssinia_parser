# Bank Document Parser

A Django web application for parsing and digitizing bank documents using OCR and LLM technology.

## Setup Instructions

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Environment Configuration
1. Copy `.env.example` to `.env`
2. Set the minimal variables:
   - `SECRET_KEY` (any random string in dev)
   - `DEBUG` (True in dev, False in prod)
   - `ALLOWED_HOSTS` (comma-separated; include `.railway.app` for Railway)
   - `CSRF_TRUSTED_ORIGINS` (include `https://*.railway.app` for Railway)
   - `GEMINI_API_KEY` (required; Google Generative AI)
   - `GEMINI_MODEL` (default: `gemini-2.5-pro`, falls back to `gemini-1.5-pro`)
   - `GEMINI_USE_VISION` (`true` to send images/PDF pages directly to Gemini Vision)
   - `GEMINI_TEMPERATURE` (default `0.15`) and `GEMINI_MAX_OUTPUT_TOKENS` (default `4000`) for consistent JSON output
   - Optional Tesseract tuning for handwriting:
     - `TESSERACT_PSM` (e.g. `11` for sparse text)
     - `TESSERACT_OEM` (`1` = LSTM only, `3` = default)
     - `TESSERACT_LANG` (default `eng+amh`)

This simplified app is stateless and does not require a database for its core flow.

### 3. Run Development Server
```bash
python manage.py runserver
```

## Features
- Upload bank-related tables as images (JPG/JPEG/PNG) or PDF
- OCR text extraction using Tesseract and minimal preprocessing
- LLM-powered structuring using Gemini, exported to Excel (.xlsx) or embedded-text PDF
- Optional typo correction and normalization when highly confident (dates, numbers, currencies)

## Requirements
- Python 3.10+
- Tesseract OCR installed on system (or use Docker image)
- Google Gemini API key

## Docker (recommended for deployment)

Build and run locally:
```bash
docker build -t bank-parser .
docker run -p 8000:8000 --env-file .env bank-parser
```

The container runs Gunicorn and binds to `$PORT` if set (Railway), otherwise 8000.

## Deploy on Railway
1. Push this repo to GitHub.
2. Create a new Railway project from the repo.
3. Set environment variables in Railway:
   - `SECRET_KEY`
   - `DEBUG=False`
   - `ALLOWED_HOSTS=.railway.app`
   - `CSRF_TRUSTED_ORIGINS=https://*.railway.app`
   - `GEMINI_API_KEY`
   - Optionally `USE_WHITENOISE=True`
4. Railway will build using the provided `Dockerfile` and run Gunicorn.

## Usage
1. Open the root URL.
2. Upload an image or PDF of a bank table.
3. Choose output format (Excel or PDF) on the form.
4. Receive the cleaned download in your chosen format. If Excel is not feasible, a structured PDF is returned, or the original/converted PDF as fallback.

## High-quality handwriting OCR
- Set `GEMINI_USE_VISION=true` to let Gemini analyze images directly (recommended for messy handwriting). The model used defaults to `GEMINI_MODEL` (default `gemini-2.5-pro`) with a safe fallback.
- If not using Vision, the app uses Tesseract OCR first, then Gemini to structure. You can tweak Tesseract with `TESSERACT_PSM`, `TESSERACT_OEM`, and `TESSERACT_LANG` (default `eng+amh`).
- You can also tune `GEMINI_TEMPERATURE` and `GEMINI_MAX_OUTPUT_TOKENS` to bias toward consistent JSON and enable larger outputs.