"""Reading a file into text, page by page, and saying how it was read.

    pdf-text     the PDF's own text layer (pdfplumber, else pypdf)
    text         a text file
    ocr-model    a scan transcribed by the connected model (vision)
    ocr-local    a scan read by Tesseract on this machine, when it is installed
    ocr-sidecar  a `<file>.ocr.txt` kept next to a bundled sample scan, so the demo runs without a model
    none         nothing could be read: the document is kept, flagged, and never guessed at
"""
from __future__ import annotations

import hashlib
import io
from pathlib import Path
from typing import Any

IMAGE_MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp", ".gif": "image/gif"}
MIME = {".pdf": "application/pdf", ".txt": "text/plain", ".md": "text/plain", **IMAGE_MIME}
MAX_BYTES = 15 * 1024 * 1024
MAGIC = {".pdf": b"%PDF", ".png": b"\x89PNG", ".jpg": b"\xff\xd8", ".jpeg": b"\xff\xd8", ".gif": b"GIF8", ".webp": b"RIFF"}
OCR_PROMPT = ("Transcribe every piece of text in this document image exactly as printed, top to bottom, keeping each label with its value on one line "
              "('Label: value'). Do not summarise, correct or add anything. Reply with the transcription only.")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def check_file(name: str, data: bytes) -> list[dict[str, str]]:
    """Intake checks on one file. These are format and integrity checks, not a malware scan."""
    ext = Path(name).suffix.lower()
    checks = [{"check": "type accepted", "status": "pass" if ext in MIME else "fail", "detail": ext or "no extension"},
              {"check": "size within limit", "status": "pass" if 0 < len(data) <= MAX_BYTES else "fail", "detail": f"{len(data):,} bytes"}]
    if ext in MAGIC:
        ok = data[:8].startswith(MAGIC[ext])
        checks.append({"check": "content matches type", "status": "pass" if ok else "fail", "detail": "signature " + ("matches" if ok else "does not match") + f" {ext}"})
    return checks


def read(name: str, data: bytes, *, model: Any = None, sidecar: str | None = None) -> dict[str, Any]:
    """{'pages': [text per page], 'text': str, 'method': str, 'note': str}"""
    ext = Path(name).suffix.lower()
    if ext in (".txt", ".md"):
        return _out([data.decode("utf-8", errors="replace")], "text")
    if ext == ".pdf":
        pages = _pdf_pages(data)
        if any(p.strip() for p in pages):
            return _out(pages, "pdf-text")
        return _scan(name, data, "application/pdf", model, sidecar, note="the PDF has no text layer")
    if ext in IMAGE_MIME:
        return _scan(name, data, IMAGE_MIME[ext], model, sidecar)
    return _out([], "none", note=f"unsupported file type {ext or '(none)'}")


def _out(pages: list[str], method: str, note: str = "") -> dict[str, Any]:
    pages = [p.replace("\r\n", "\n").replace("\r", "\n") for p in pages]
    return {"pages": pages, "text": "\n".join(pages), "method": method, "note": note}


def _pdf_pages(data: bytes) -> list[str]:
    try:
        import pdfplumber

        with pdfplumber.open(io.BytesIO(data)) as pdf:
            return [(p.extract_text() or "") for p in pdf.pages]
    except ImportError:
        pass
    except Exception:
        return []
    try:
        from pypdf import PdfReader

        return [(p.extract_text() or "") for p in PdfReader(io.BytesIO(data)).pages]
    except Exception:
        return []


def _scan(name: str, data: bytes, mime: str, model: Any, sidecar: str | None, note: str = "") -> dict[str, Any]:
    if model is not None and not getattr(model, "offline", True) and mime != "application/pdf":
        try:
            text = model.text("You transcribe documents exactly.", OCR_PROMPT, images=[(data, mime)], step="ocr")
            if text.strip():
                return _out([text], "ocr-model", note)
        except Exception as exc:
            note = f"{note}; the model could not read it ({type(exc).__name__})".strip("; ")
    local = _tesseract(data) if mime != "application/pdf" else ""
    if local.strip():
        return _out([local], "ocr-local", note)
    if sidecar and sidecar.strip():
        return _out([sidecar], "ocr-sidecar", (note + "; " if note else "") + "read from the sample's bundled transcription")
    return _out([], "none", (note + "; " if note else "") + "no model or OCR engine could read this scan")


def _tesseract(data: bytes) -> str:
    try:
        import pytesseract
        from PIL import Image

        return pytesseract.image_to_string(Image.open(io.BytesIO(data)))
    except Exception:
        return ""
