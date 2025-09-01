# Abyssinia Parser — Aggressive Simplification Plan

Goal: cut the project down to only the four requirements and nothing else.

Must-have features only:
1) Upload an image of paper writing (organized/semi-organized tables or related bank data; for now: table data).
2) Process image and clean it for OCR.
3) Output clean, structured data in spreadsheet form (Excel; optionally CSV; Google Sheets export can be added later via a simple API call).
4) Done. No sessions, no DB, no Supabase, no cleanup scheduler, no PDF/DOC, no multi-user controls, no overengineered flows.


## Target Architecture (after simplification)
- Django minimal app, single page.
- Stateless processing in-memory; no database and no cloud storage.
- Minimal endpoints:
  - GET `/` → upload page (`parser/upload.html`).
  - POST `/process/` → accepts file; pipeline: preprocess → OCR → Gemini LLM structure → Excel export; returns file download or JSON + file stream.
- Minimal modules:
  - `parser/forms.py` → `DocumentUploadForm` (restrict to images/PDF, 10MB limit).
  - `parser/ocr_pipeline.py` (new) → preprocess (Pillow), OCR (pytesseract, PyMuPDF for PDFs), structure via Gemini (`google-generativeai`), export to Excel (`openpyxl`).
  - `parser/views.py` → 2 views only: `upload()` and `process()` (or `UploadView` + `process`). No AJAX endpoints unless necessary.
- Minimal UI: one template `parser/templates/parser/upload.html` and one small JS (optional) for form submit; 1 small CSS file (optional).
- Settings: SQLite default; no Supabase; `GEMINI_API_KEY` from environment; small media/temp dir if needed, but prefer in-memory.


## What to DELETE (out of scope)
Delete the following files/directories entirely:
- Cloud/storage/cleanup/session systems:
  - `parser/management/` directory (all commands):
    - `cleanup_files.py`, `scheduled_cleanup.py`, `test_cleanup.py`, `test_db_connection.py`, `test_error_handling.py`.
  - `parser/middleware.py` (both middlewares).
  - `parser/models.py` (and all models).
  - `parser/migrations/` (all migrations).
  - Supabase integration and file storage functionality in `parser/services.py` (remove or replace the file completely).
- Extra output formats and heavy generators:
  - Remove PDF generation (ReportLab) and DOC generation (python-docx) code from `parser/services.py`.
- Extra endpoints and views not required by 4 core features:
  - In `parser/views.py`: remove `DocumentUploadView` complexity, `upload_ajax`, `retry_document_processing`, `get_processing_status`, `cleanup_session`, `get_cleanup_info`, `get_document_results`, `download_file` (we will instead return the generated Excel directly from the `/process/` view).
- Templates not needed:
  - `parser/templates/parser/error.html` and `parser/templates/parser/partials/*`.
  - `debug_upload.html` at repo root.
- Static assets not needed:
  - Replace `parser/static/parser/js/upload.js` and `parser/static/parser/css/upload.css` with minimal or remove entirely if not needed.
- Documentation that reflects removed systems:
  - `CLEANUP_SETUP.md`, `DATABASE_SETUP.md` — delete.
  - Replace `OCR_IMPLEMENTATION.md` with a short section inside README about the minimal pipeline (optional) or delete it.
  - Replace `PROJECT_REQUIREMENTS.md` with a short, current scope (or delete).


## What to KEEP (and refactor)
- Project scaffolding:
  - `manage.py`, `document_parser/asgi.py`, `document_parser/wsgi.py`.
  - `document_parser/urls.py` → keep but route only to minimal `parser.urls`.
- App basics:
  - `parser/forms.py` → keep but simplify validation message copy; restrict to `.jpg,.jpeg,.png,.pdf` only.
  - `parser/templates/parser/upload.html` → keep and simplify.
- OCR + LLM + Excel logic:
  - Build a new minimal `parser/ocr_pipeline.py` to contain: `preprocess_image()`, `extract_text_from_image()`, `extract_text_from_pdf()`, `call_gemini_to_structure()`, `to_excel()`.
  - Update `parser/views.py` to use only this pipeline.


## Dependencies — prune aggressively
Replace `requirements.txt` with only what’s required for the minimal pipeline:
- Keep: `Django`, `pytesseract`, `google-generativeai`, `openpyxl`, `Pillow`, `PyMuPDF`, `python-dotenv` (optional but handy).
- Remove: `openai`, `supabase`, `reportlab`, `python-docx`, `psycopg2-binary`, `requests` (unless we need it explicitly; Gemini SDK handles its own HTTP).

Proposed minimal `requirements.txt`:
```
Django==5.2.5
pytesseract==0.3.13
google-generativeai==0.8.3
openpyxl==3.1.5
Pillow==10.4.0
PyMuPDF==1.24.10
python-dotenv==1.0.1
```


## Settings — simplify
Edit `document_parser/settings.py`:
- Remove Supabase configuration block and env vars: `SUPABASE_URL`, `SUPABASE_KEY`, `SUPABASE_SERVICE_KEY`, `SUPABASE_BUCKET_NAME`.
- Remove dynamic DB switching and PostgreSQL config; always use default SQLite.
- Remove explicit session customization (we’re stateless).
- Ensure `DEBUG` and `SECRET_KEY` come from `.env` (optional) and default sane values for local dev.
- Remove `STATIC_ROOT` if not needed; keep `STATIC_URL` only for minimal static.
- Add `GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")`; do not set insecure defaults.


## URLs — simplify
- `document_parser/urls.py`: keep `path('', include('parser.urls'))` and remove extras.
- `parser/urls.py`: only two routes remain:
  - `path('', views.upload, name='upload')`
  - `path('process/', views.process, name='process')`


## Views — rewrite minimal
Implement two small views in `parser/views.py`:
- `upload(request)` (GET): render `parser/upload.html` with a simple form.
- `process(request)` (POST):
  - Validate file via `DocumentUploadForm`.
  - Route by extension:
    - JPG/PNG → `preprocess_image()` → `extract_text_from_image()`.
    - PDF → `extract_text_from_pdf()` (use PyMuPDF to render to images if needed, then OCR).
  - Call `call_gemini_to_structure(raw_text)` to produce structured JSON for table(s).
  - `to_excel(structured)` to create a workbook in-memory (`BytesIO`) and return as `HttpResponse` with content-disposition attachment.
  - On failure, return a small JSON error or render a message on the same page.

Note: no DB writes, no sessions, no storage. All ephemeral.


## New module — `parser/ocr_pipeline.py`
Create a single, tight module with functions:
- `preprocess_image(image_bytes) -> PIL.Image`: grayscale, contrast, resize if needed (Pillow only).
- `extract_text_from_image(image: PIL.Image) -> str`: `pytesseract.image_to_string` with configs optimized for tables (e.g., `--psm 6` etc.).
- `extract_text_from_pdf(file_obj) -> str`: use `fitz` to iterate pages, rasterize to images, OCR each, join text.
- `call_gemini_to_structure(text: str) -> dict`: prompt Gemini to output a JSON schema like:
  ```json
  { "tables": [ { "name": "main", "headers": ["col1", ...], "rows": [["..."], ...] } ] }
  ```
  - Validate and coerce to this minimal schema.
- `to_excel(structured: dict) -> bytes`: write a workbook with one sheet per table.

Security & errors:
- If Tesseract missing, return a clear error message.
- If GEMINI_API_KEY missing, return a clear error message.


## Templates — simplify UI
- Keep `parser/templates/parser/upload.html` only. Remove `partials/`, `error.html`.
- Content: basic `<form method="post" enctype="multipart/form-data">` with CSRF, a file input, and a submit button.
- Optionally show a small success/error alert above the form.


## Static — optional minimal
- Delete existing `upload.js` and `upload.css`.
- If needed, add tiny inline styles in the template.


## File-by-file action list (exact)
Root:
- Delete: `debug_upload.html`, `CLEANUP_SETUP.md`, `DATABASE_SETUP.md`, `PROJECT_REQUIREMENTS.md` (or archive), `OCR_IMPLEMENTATION.md` (or fold into README).
- Update: `README.md` to only document the 4 features and quickstart.
- Update: `requirements.txt` (prune per above).

`document_parser/`:
- `settings.py`: remove Supabase + Postgres + sessions; add `GEMINI_API_KEY` env; keep SQLite.
- `urls.py`: unchanged except it includes `parser.urls`.

`parser/`:
- Delete: `models.py`, `migrations/`, `middleware.py`, `management/` directory, `services_backup.py`.
- Replace: `services.py` with nothing OR delete it entirely and move minimal logic to `ocr_pipeline.py`.
- Update: `forms.py` (keep but simplify messages; restrict to images/PDF; allow `.txt` only if you want text passthrough — otherwise remove).
- Replace: `views.py` with two functions: `upload` (GET), `process` (POST) as described.
- Update: `urls.py` to only map `''` → `upload` and `'process/'` → `process`.
- Templates: keep `templates/parser/upload.html`; delete `templates/parser/error.html` and `templates/parser/partials/*`.
- Static: delete `static/parser/js/upload.js` and `static/parser/css/upload.css` (unless you decide to keep minimal styling).


## Environment
- `.env` should contain only:
  - `SECRET_KEY`
  - `DEBUG`
  - `GEMINI_API_KEY`
- If on Windows with Tesseract not on PATH, you may optionally set `TESSERACT_CMD` pointing to `C:\\Program Files\\Tesseract-OCR\\tesseract.exe` and reference it in the pipeline if needed.


## Acceptance criteria
- Uploading an image or PDF produces an Excel download with structured table(s) derived via OCR + Gemini.
- No DB tables are created or used; no Supabase/network storage is required.
- No PDF/DOC outputs are generated.
- Only two routes are available and work: `/` and `/process/`.
- `requirements.txt` contains only the minimal set.


## Step-by-step execution plan (for an AI agent)
1) Prune dependencies: rewrite `requirements.txt` to the minimal list above.
2) Delete out-of-scope files/dirs listed in “What to DELETE”.
3) `document_parser/settings.py` edits:
   - Remove Supabase and Postgres blocks; remove session config; add `GEMINI_API_KEY` env lookup; ensure SQLite default.
4) `parser/urls.py`: replace with only two endpoints: `upload`, `process`.
5) `parser/views.py`: replace contents with two small views using `ocr_pipeline`.
6) Create `parser/ocr_pipeline.py` with the described functions and minimal robust error handling.
7) `parser/forms.py`: simplify to allow `.jpg,.jpeg,.png,.pdf` only (10MB), remove extra validation branches not needed.
8) Templates: replace `parser/templates/parser/upload.html` with a minimal form and inline feedback.
9) Static: delete existing heavy files; optional minimal inline styling remains.
10) README: rewrite to reflect the 4 requirements, setup (`pip install -r requirements.txt`, set `GEMINI_API_KEY`, install Tesseract), run (`python manage.py runserver`), and usage.
11) Test run: try a sample image; verify Excel is downloaded; validate that no DB or external storage is touched.


## Risks and mitigations
- Tesseract not installed → show clear error and instructions; allow `.txt` passthrough as a fallback (optional).
- Gemini rate limits or auth → show clear error; allow returning raw OCR text if structuring fails.
- OCR quality varies → keep preprocessing simple but modular for future tuning.


## Out-of-scope and explicitly removed
- Supabase storage, database models, and any concurrency/session limiting.
- Cleanup schedulers and management commands.
- PDF and DOC outputs.
- Multi-step AJAX flows, progress endpoints, retry endpoints, status endpoints.
- Any OpenAI usage (we use Gemini only).


---
This plan is intentionally aggressive and minimal. It provides a clear, linear set of edits so an AI agent can immediately start deleting and rewriting files to meet the 4 core requirements only.
