import io
import json
import os
from typing import Dict, Any, List
from datetime import datetime

from PIL import Image, ImageOps, ImageEnhance, ImageFilter
import fitz  # PyMuPDF
from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter

try:
    import google.generativeai as genai
except Exception:  # pragma: no cover
    genai = None


# --- Image helpers ---

def preprocess_image(image_bytes: bytes) -> Image.Image:
    image = Image.open(io.BytesIO(image_bytes))
    # Convert to grayscale
    image = image.convert("L")
    # Upscale to help OCR on handwriting
    try:
        w, h = image.size
        image = image.resize((int(w * 2), int(h * 2)), Image.LANCZOS)
    except Exception:
        pass
    # Enhance contrast and sharpness
    image = ImageEnhance.Contrast(image).enhance(1.8)
    image = ImageOps.autocontrast(image)
    image = image.filter(ImageFilter.MedianFilter(size=3))
    image = ImageEnhance.Sharpness(image).enhance(1.6)
    return image

def images_from_pdf(file_obj) -> List[Image.Image]:
    # Return PIL images for all pages at higher DPI for better OCR
    data = file_obj.read()
    doc = fitz.open(stream=data, filetype="pdf")
    images: List[Image.Image] = []
    for page in doc:
        pix = page.get_pixmap(dpi=300)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        images.append(img)
    doc.close()
    return images


# --- Structuring with Gemini Vision ---

def _get_gemini_model_name() -> str:
    # Default to 2.5 Flash for Vision; fallback set separately
    return os.getenv("GEMINI_MODEL", "gemini-2.5-flash")


def _make_model():
    """Create a GenerativeModel, falling back if the requested model isn't available."""
    name = _get_gemini_model_name()
    try:
        return genai.GenerativeModel(name)
    except Exception:
        fb = os.getenv("GEMINI_FALLBACK_MODEL", "gemini-2.5-flash-lite")
        return genai.GenerativeModel(fb)


def _get_gen_config() -> Dict[str, Any]:
    """Generation config for higher-quality, consistent JSON output."""
    try:
        temp = float(os.getenv("GEMINI_TEMPERATURE", "0.15"))
    except Exception:
        temp = 0.15
    try:
        mot = int(os.getenv("GEMINI_MAX_OUTPUT_TOKENS", "4000"))
    except Exception:
        mot = 4000
    return {
        "temperature": temp,
        "top_p": 0.9,
        "top_k": 40,
        "max_output_tokens": mot,
    }

def _image_to_part(img: Image.Image) -> Dict[str, Any]:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return {"mime_type": "image/png", "data": buf.getvalue()}


def structure_with_gemini_vision(images: List[Image.Image]) -> Dict[str, Any]:
    """Use Gemini Vision to directly extract tabular data from images."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key or genai is None or not images:
        # Fallback to empty text structure
        return _fallback_structure("")

    genai.configure(api_key=api_key)
    model = _make_model()
    prompt = (
        "You are an expert multilingual document and table parser for banking PDFs and scans.\n"
        "The pages may contain English and Amharic (Ethiopic). Detect languages automatically.\n"
        "Goal: produce clean, analysis-ready tables that will be exported to Excel.\n\n"
        "Return STRICT JSON ONLY with this schema:\n"
        "{\n  \"tables\": [ { \"name\": string, \"headers\": [string], \"rows\": [[string]] } ]\n}\n\n"
        "Instructions (apply when confident; otherwise keep original text):\n"
        "- Preserve original language in cells; do not transliterate Amharic.\n"
        "- Fix obvious OCR artifacts (0/O, 1/l, repeated headers) only when highly confident.\n"
        "- For dates, prefer ISO YYYY-MM-DD if unambiguous; otherwise keep as seen.\n"
        "- Numbers: normalize digits and decimal separators; keep currency symbol or code with the amount (e.g., ETB 1,234.50).\n"
        "- Infer headers if missing using common banking columns: Date, Description, Debit, Credit, Balance, Currency.\n"
        "- Reconstruct irregular tables; merge split cells; ensure consistent column counts; deduplicate.\n"
        "- If content is key:value, output a two-column table [key, value]. If free-form, output a single-column table, one line per row.\n"
        "- Sort rows by date if a clear date column exists; otherwise preserve order.\n"
        "- Output JSON only. No comments or markdown.\n"
    )

    parts: List[Any] = [prompt, "\n--- IMAGES START ---\n"]
    for img in images:
        parts.append(_image_to_part(img))
    parts.append("\n--- IMAGES END ---\n")

    response = model.generate_content(parts, generation_config=_get_gen_config())
    out = response.text.strip() if hasattr(response, "text") else "{}"
    try:
        data = json.loads(_extract_json(out))
        if not isinstance(data, dict) or "tables" not in data:
            return _fallback_structure("")
        return data
    except Exception:
        return _fallback_structure("")


def _extract_json(s: str) -> str:
    # Remove fencing if present
    s = s.strip()
    if s.startswith("```"):
        s = s.strip("`\n")
        # Drop potential leading 'json' token
        if s.lstrip().startswith("json"):
            s = s.split("\n", 1)[1] if "\n" in s else "{}"
    return s


# --- PDF export fallback ---

def images_to_pdf(images: List[Image.Image]) -> bytes:
    """Create a simple multi-page PDF from one or more PIL images.
    Keeps original image fidelity (best for multilingual scripts like Amharic)."""
    if not images:
        return b""
    rgb_images: List[Image.Image] = []
    for im in images:
        if im.mode != "RGB":
            rgb_images.append(im.convert("RGB"))
        else:
            rgb_images.append(im)
    buf = io.BytesIO()
    first, rest = rgb_images[0], rgb_images[1:]
    first.save(buf, format="PDF", save_all=True, append_images=rest)
    return buf.getvalue()


def _fallback_structure(text: str) -> Dict[str, Any]:
    # Very naive: split lines, split on whitespace, first row as headers if looks tabular
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    rows = [ln.split() for ln in lines]
    headers: List[str]
    body: List[List[str]]
    if rows and all(len(r) == len(rows[0]) for r in rows[1:]):
        headers = [f"col{i+1}" for i in range(len(rows[0]))]
        body = rows
    else:
        headers = ["text"]
        body = [[ln] for ln in lines]

    return {
        "tables": [
            {"name": "main", "headers": headers, "rows": body}
        ]
    }


# --- Excel export ---

def to_excel(structured: Dict[str, Any]) -> bytes:
    wb = Workbook()
    # Remove default sheet
    ws0 = wb.active
    wb.remove(ws0)

    def _parse_cell(val: Any):
        # Try to coerce numbers (including 1,234.56) and ISO-like dates
        if isinstance(val, (int, float)):
            return val
        s = str(val).strip()
        # Try ISO date
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d"):
            try:
                dt = datetime.strptime(s, fmt).date()
                return dt
            except Exception:
                pass
        # Remove currency symbols for numeric parse, keep as float
        try:
            # Replace common thousands separators
            num = s.replace(",", "").replace("ETB", "").replace("USD", "").strip()
            if num and (num.replace(".", "", 1).lstrip("-+").isdigit()):
                return float(num)
        except Exception:
            pass
        return s

    for table in structured.get("tables", []):
        title = table.get("name") or "Sheet"
        title = title[:31]  # Excel sheet name limit
        ws = wb.create_sheet(title)
        headers = table.get("headers", [])
        rows = table.get("rows", [])
        if headers:
            ws.append(headers)
            # Bold header row
            for col_idx in range(1, len(headers) + 1):
                cell = ws.cell(row=1, column=col_idx)
                cell.font = Font(bold=True)
            # Freeze header row
            ws.freeze_panes = "A2"
        for r in rows:
            parsed = [_parse_cell(c) if c is not None else "" for c in r]
            ws.append(parsed)

        # Basic column width adjustment based on max length in first 200 rows
        max_cols = max(len(headers), max((len(r) for r in rows), default=0))
        for col_idx in range(1, max_cols + 1):
            col_letter = get_column_letter(col_idx)
            max_len = 0
            for row_idx, row in enumerate(ws.iter_rows(min_row=1, max_row=min(ws.max_row, 200), min_col=col_idx, max_col=col_idx), start=1):
                val = row[0].value
                if val is None:
                    continue
                s = str(val)
                if len(s) > max_len:
                    max_len = len(s)
            ws.column_dimensions[col_letter].width = min(max(10, max_len + 2), 50)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
