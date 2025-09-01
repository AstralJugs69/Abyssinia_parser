import io
import json
import os
from typing import Dict, Any, List

import pytesseract
from PIL import Image, ImageOps, ImageEnhance, ImageFilter
import fitz  # PyMuPDF
from openpyxl import Workbook

try:
    import google.generativeai as genai
except Exception:  # pragma: no cover
    genai = None


# --- OCR helpers ---

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


def extract_text_from_image(image: Image.Image) -> str:
    # Configurable Tesseract settings for better handwriting OCR
    psm = os.getenv("TESSERACT_PSM", "6")  # 6: block of text; 11: sparse text; 7: single line
    oem = os.getenv("TESSERACT_OEM", "3")  # 1: LSTM only, 3: default
    # Default to multilingual English + Amharic (Ethiopic)
    lang = os.getenv("TESSERACT_LANG", "eng+amh")
    config = f"--oem {oem} --psm {psm} -l {lang}"
    return pytesseract.image_to_string(image, config=config)


def extract_text_from_pdf(file_obj) -> str:
    # file_obj: Django UploadedFile or file-like
    data = file_obj.read()
    doc = fitz.open(stream=data, filetype="pdf")
    texts: List[str] = []
    for page in doc:
        pix = page.get_pixmap(dpi=300)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        texts.append(extract_text_from_image(img))
    doc.close()
    return "\n".join(texts)

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


# --- Structuring with Gemini ---

def _get_gemini_model_name() -> str:
    # Allow configuration; default to user's requested high-quality model
    return os.getenv("GEMINI_MODEL", "gemini-2.5-pro")


def _make_model():
    """Create a GenerativeModel, falling back if the requested model isn't available."""
    name = _get_gemini_model_name()
    try:
        return genai.GenerativeModel(name)
    except Exception:
        fb = os.getenv("GEMINI_FALLBACK_MODEL", "gemini-1.5-pro")
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


def call_gemini_to_structure(text: str) -> Dict[str, Any]:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key or genai is None:
        # Fallback: naive structure
        return _fallback_structure(text)

    genai.configure(api_key=api_key)
    model = _make_model()
    prompt = (
        "You are an expert multilingual document parser for noisy bank statements and handwritten tables.\n"
        "Input may contain English and Amharic (Ethiopic) text, or mixed languages. Detect language automatically.\n"
        "Goal: return high-quality, CLEAN tables even from messy or nonsensical structures.\n\n"
        "Output STRICT JSON ONLY with this schema:\n"
        "{\n  \"tables\": [ { \"name\": string, \"headers\": [string], \"rows\": [[string]] } ]\n}\n\n"
        "Cleaning and structuring rules (apply only when confident, otherwise keep raw):\n"
        "- Preserve original language in cells (Amharic/English).\n"
        "- Correct obvious typos and OCR mistakes only when HIGHLY confident (e.g., 0/O, 1/l).\n"
        "- Normalize dates to ISO YYYY-MM-DD when unambiguous.\n"
        "- Normalize numbers to standard digits and decimal separators; preserve currency symbol/code if present.\n"
        "- Infer headers when missing; use typical banking headers when appropriate (Date, Description, Debit, Credit, Balance).\n"
        "- Reconstruct irregular tables, merge split cells, remove repeated header rows, and deduplicate duplicate rows.\n"
        "- Ensure consistent column count for all rows; fill missing cells with empty strings.\n"
        "- Sort rows by date if a clear date column exists; otherwise preserve input order.\n"
        "- If data is semi-structured (key:value), output a two-column table [key, value].\n"
        "- If tabularization is impossible, output a single-column table with one item per line.\n"
        "- Output JSON only—NO commentary, headings, or Markdown.\n"
    )

    response = model.generate_content([
        prompt,
        "\n--- OCR TEXT START ---\n",
        text,
        "\n--- OCR TEXT END ---\n",
    ], generation_config=_get_gen_config())

    out = response.text.strip() if hasattr(response, "text") else "{}"
    try:
        data = json.loads(_extract_json(out))
        # Basic validation
        if not isinstance(data, dict) or "tables" not in data:
            return _fallback_structure(text)
        return data
    except Exception:
        return _fallback_structure(text)

def should_use_gemini_vision() -> bool:
    """Decide whether to use Gemini Vision for OCR + structuring."""
    use = os.getenv("GEMINI_USE_VISION", "false").lower() in {"1", "true", "yes"}
    api_key = os.getenv("GEMINI_API_KEY")
    return bool(use and api_key and genai is not None)


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
        "You are an expert multilingual document parser for noisy bank statements and handwritten tables.\n"
        "Images may contain English and Amharic (Ethiopic) text. Detect languages automatically.\n"
        "Goal: return high-quality, CLEAN tables even from messy or nonsensical structures.\n\n"
        "Output STRICT JSON ONLY with this schema:\n"
        "{\n  \"tables\": [ { \"name\": string, \"headers\": [string], \"rows\": [[string]] } ]\n}\n\n"
        "Cleaning and structuring rules (apply only when confident, otherwise keep raw):\n"
        "- Preserve original language in cells (Amharic/English).\n"
        "- Correct obvious typos and OCR mistakes only when HIGHLY confident (e.g., 0/O, 1/l).\n"
        "- Normalize dates to ISO YYYY-MM-DD when unambiguous.\n"
        "- Normalize numbers to standard digits and decimal separators; preserve currency symbol/code if present.\n"
        "- Infer headers when missing; use typical banking headers when appropriate (Date, Description, Debit, Credit, Balance).\n"
        "- Reconstruct irregular tables, merge split cells, remove repeated header rows, and deduplicate duplicate rows.\n"
        "- Ensure consistent column count for all rows; fill missing cells with empty strings.\n"
        "- Sort rows by date if a clear date column exists; otherwise preserve input order.\n"
        "- If data is semi-structured (key:value), output a two-column table [key, value].\n"
        "- If tabularization is impossible, output a single-column table with one item per line.\n"
        "- Output JSON only—NO commentary, headings, or Markdown.\n"
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

    for table in structured.get("tables", []):
        title = table.get("name") or "Sheet"
        title = title[:31]  # Excel sheet name limit
        ws = wb.create_sheet(title)
        headers = table.get("headers", [])
        rows = table.get("rows", [])
        if headers:
            ws.append(headers)
        for r in rows:
            ws.append([str(c) if c is not None else "" for c in r])

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
