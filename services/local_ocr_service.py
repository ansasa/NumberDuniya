"""Offline, read-only OCR for NumberDuniya PDF/JPEG/PNG documents.

Uses PyMuPDF, Pillow and Tesseract CLI. No pandas, pytesseract,
PyArrow, Gemini or Supabase. OCR candidates are NOT verified results.
"""
from __future__ import annotations

import io
import os
import re
import subprocess
import tempfile
from pathlib import Path

import pymupdf
from PIL import Image, ImageEnhance, ImageOps, ImageFilter, UnidentifiedImageError

MAX_FILE_SIZE = 10 * 1024 * 1024
MAX_PAGES = 30
MAX_IMAGE_PIXELS = 40_000_000
TESSERACT_DEFAULT = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
ALLOWED_MIME_TYPES = {"application/pdf", "image/jpeg", "image/png"}
Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS


def _tesseract_executable() -> str:
    executable = os.environ.get("TESSERACT_CMD", TESSERACT_DEFAULT)
    if not Path(executable).is_file():
        raise RuntimeError(
            f"Tesseract executable not found at {executable}. "
            "Set TESSERACT_CMD to its full executable path."
        )
    return executable


def _run_tesseract(image: Image.Image, psm: int) -> str:
    with tempfile.TemporaryDirectory(prefix="numberduniya_ocr_") as tmpdir:
        image_path = Path(tmpdir) / "input.png"
        image.save(image_path, format="PNG")
        command = [
            _tesseract_executable(), str(image_path), "stdout",
            "-l", "eng", "--psm", str(psm),
        ]
        try:
            result = subprocess.run(
                command, capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=90,
                check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("Local OCR timed out after 90 seconds.") from exc
        if result.returncode != 0:
            raise RuntimeError(
                "Tesseract OCR failed: "
                + (result.stderr.strip() or "unknown error")[:500]
            )
        return result.stdout.strip()


def _prepare_image(image: Image.Image) -> Image.Image:
    image = ImageOps.exif_transpose(image)
    if image.width * image.height > MAX_IMAGE_PIXELS:
        raise ValueError("Image resolution exceeds OCR safety limit.")
    return image.convert("RGB")


def _enhance_image(image: Image.Image) -> Image.Image:
    gray = ImageOps.grayscale(image)
    gray = ImageOps.autocontrast(gray, cutoff=1)
    gray = ImageEnhance.Contrast(gray).enhance(1.35)
    return gray.filter(ImageFilter.UnsharpMask(radius=1, percent=120, threshold=3))


def _score_candidate(text: str) -> tuple[int, int, int]:
    """Heuristic for choosing a preview, NOT an accuracy guarantee."""
    lines = text.splitlines()
    four_digit_tokens = sum(
        len(re.findall(r"(?<!\d)\d{4}(?!\d)", line))
        for line in lines
    )
    prize_mentions = len(re.findall(r"\bprize\b", text, flags=re.IGNORECASE))
    return (four_digit_tokens, prize_mentions, len(text.strip()))


def _ocr_image(image: Image.Image) -> tuple[str, list[dict], str]:
    prepared = _prepare_image(image)
    # Keep the original extraction for comparison; enhanced PSM 6 is an
    # additional candidate, not an automatic claim of greater correctness.
    candidates = []
    for name, source, psm in (
        ("original_psm3", prepared, 3),
        ("enhanced_psm6", _enhance_image(prepared), 6),
    ):
        text = _run_tesseract(source, psm)
        candidates.append({
            "name": name,
            "psm": psm,
            "text": text,
            "characters": len(text),
            "four_digit_tokens": _score_candidate(text)[0],
        })
    selected = max(candidates, key=lambda c: _score_candidate(c["text"]))
    return selected["text"], candidates, selected["name"]



# Fractions of page height, calibrated from the supplied Nagaland 8 PM
# Magic Sunday layout. The advertisement is between 0.505 and 0.752.
# This is a *specific* profile, never applied to unrelated lottery layouts.
REGION_PROFILES = {
    "nagaland_magic_sunday_8pm": (
        ("header", 0.000, 0.210),
        ("first_prize", 0.180, 0.300),
        ("prizes_2_to_4", 0.285, 0.505),
        ("prize_5", 0.752, 0.965),
        ("footer", 0.960, 1.000),
    ),
}


def _ocr_region_image(image: Image.Image, profile: str, first_prize_image: Image.Image | None = None) -> tuple[str, list[dict]]:
    """OCR only selected vertical bands; leave the source image unchanged."""
    if profile not in REGION_PROFILES:
        raise ValueError(f"Unknown OCR layout profile: {profile}")
    source = _prepare_image(image)
    output = []
    regions = []
    for name, top, bottom in REGION_PROFILES[profile]:
        y0 = int(source.height * top)
        y1 = min(source.height, max(y0 + 1, int(source.height * bottom)))
        crop = source.crop((0, y0, source.width, y1))
        if name == "first_prize":
            if first_prize_image is not None:
                focus = _prepare_image(first_prize_image)
                crop = focus.crop((0, int(focus.height * 0.17),
                                   focus.width, int(focus.height * 0.30)))
            # Proven diagnostic configuration: untouched pixels, PSM 11.
            # Use a separate 3x PDF rendering when available (see below).
            text = _run_tesseract(crop, 11)
            candidates = [{"name": "original_psm11_focus", "psm": 11,
                           "text": text, "characters": len(text),
                           "four_digit_tokens": _score_candidate(text)[0]}]
            selected = "original_psm11_focus"
        else:
            text, candidates, selected = _ocr_image(crop)
        regions.append({
            "name": name, "y_fraction": [top, bottom],
            "text": text, "selected_candidate": selected,
            "candidates": candidates,
        })
        output.append(f"--- {name.upper()} ---\n{text}")
    return "\n\n".join(output), regions


def _render_pdf_page(page: pymupdf.Page) -> Image.Image:
    zoom = 2.5
    pixels = page.rect.width * page.rect.height * zoom * zoom
    if pixels > MAX_IMAGE_PIXELS:
        zoom = min(zoom, (MAX_IMAGE_PIXELS / (page.rect.width * page.rect.height)) ** 0.5)
    pixmap = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
    with Image.open(io.BytesIO(pixmap.tobytes("png"))) as img:
        return img.convert("RGB")

def extract_local_text(
    file_bytes: bytes, file_type: str, layout_profile: str | None = None
) -> dict:
    """Return raw OCR text and page-level alternatives; never write to DB.

    layout_profile=None preserves generic OCR behavior. Explicit profile
    'nagaland_magic_sunday_8pm' skips the central advertisement. Each page
    contains OCR text; profiled pages also contain individual regions.
    Always review original document before verification/publishing.
    """
    if not isinstance(file_bytes, bytes) or not file_bytes:
        raise ValueError("File must contain non-empty bytes.")
    if len(file_bytes) > MAX_FILE_SIZE:
        raise ValueError("File exceeds the 10 MB upload limit.")
    if file_type not in ALLOWED_MIME_TYPES:
        raise ValueError("Unsupported file type. Use PDF, JPEG, or PNG.")

    if layout_profile is not None and layout_profile not in REGION_PROFILES:
        raise ValueError(f"Unknown OCR layout profile: {layout_profile}")

    pages = []
    warnings = [
        "OCR text is unverified. Compare every prize and winning number "
        "against the original document before publishing."
    ]

    if file_type == "application/pdf":
        if not file_bytes.startswith(b"%PDF-"):
            raise ValueError("Invalid PDF signature.")
        try:
            document = pymupdf.open(stream=file_bytes, filetype="pdf")
        except Exception as exc:
            raise ValueError("Cannot open PDF document.") from exc
        try:
            if document.needs_pass:
                raise ValueError("Password-protected PDFs are not supported.")
            if len(document) > MAX_PAGES:
                raise ValueError(f"PDF exceeds {MAX_PAGES} page OCR limit.")
            for index, page in enumerate(document):
                embedded = page.get_text("text").strip()
                if layout_profile is not None:
                    image = _render_pdf_page(page)
                    # The focused first-prize crop was validated at 3x,
                    # while other prize crops retain the existing 2.5x path.
                    focus_pixels = page.rect.width * page.rect.height * 9
                    focus_image = None
                    if (layout_profile == "nagaland_magic_sunday_8pm"
                            and focus_pixels <= MAX_IMAGE_PIXELS):
                        focus_pix = page.get_pixmap(
                            matrix=pymupdf.Matrix(3, 3), alpha=False)
                        focus_image = Image.frombytes(
                            "RGB", (focus_pix.width, focus_pix.height), focus_pix.samples)
                    text, regions = _ocr_region_image(image, layout_profile, focus_image)
                    pages.append({
                        "page_number": index + 1, "method": "tesseract_regions",
                        "text": text, "selected_candidate": "region_based",
                        "candidates": [], "regions": regions,
                    })
                    continue
                if len(embedded) >= 40:
                    method, text = "embedded_text", embedded
                    candidates, selected_candidate = [], "embedded_text"
                else:
                    # 2.5x rendering improves small print; cap pixel count.
                    zoom = 2.5
                    if (page.rect.width * zoom) * (page.rect.height * zoom) > MAX_IMAGE_PIXELS:
                        zoom = min(2.0, (MAX_IMAGE_PIXELS / (page.rect.width * page.rect.height)) ** 0.5)
                    pixmap = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
                    with Image.open(io.BytesIO(pixmap.tobytes("png"))) as img:
                        text, candidates, selected_candidate = _ocr_image(img)
                    method = "tesseract"
                    if not text:
                        warnings.append(f"Page {index + 1}: no readable text found.")
                pages.append({
                    "page_number": index + 1, "method": method, "text": text,
                    "selected_candidate": selected_candidate, "candidates": candidates,
                })
        finally:
            document.close()
    else:
        signature_ok = (
            file_bytes.startswith(b"\xff\xd8\xff") if file_type == "image/jpeg"
            else file_bytes.startswith(b"\x89PNG\r\n\x1a\n")
        )
        if not signature_ok:
            raise ValueError("Image content does not match its MIME type.")
        try:
            with Image.open(io.BytesIO(file_bytes)) as image:
                image.load()
                if layout_profile is not None:
                    text, regions = _ocr_region_image(image, layout_profile)
                    candidates, selected_candidate = [], "region_based"
                else:
                    text, candidates, selected_candidate = _ocr_image(image)
                    regions = []
        except (UnidentifiedImageError, OSError) as exc:
            raise ValueError("Cannot decode image file.") from exc
        pages.append({
            "page_number": 1, "method": "tesseract", "text": text,
            "selected_candidate": selected_candidate, "candidates": candidates,
            "regions": regions,
        })
        if not text:
            warnings.append("No readable text found in image.")

    return {
        "engine": "local",
        "layout_profile": layout_profile,
        "pages": pages,
        "raw_text": "\n\n".join(
            f"--- Page {page['page_number']} ---\n{page['text']}" for page in pages
        ),
        "warnings": warnings,
    }
