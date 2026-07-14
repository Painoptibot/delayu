"""Извлечение текста из документов (OCR / text layer) для модуля ИИ."""
from __future__ import annotations

import io
from typing import BinaryIO

from django.core.files.uploadedfile import UploadedFile


def extract_text_from_upload(file_obj: UploadedFile | BinaryIO, *, filename: str = "") -> dict:
    """
    Возвращает:
      text, engine, pages, warnings[]
    """
    name = (filename or getattr(file_obj, "name", "") or "").lower()
    raw = _read_bytes(file_obj)
    if not raw:
        return {"text": "", "engine": "none", "pages": 0, "warnings": ["Пустой файл"]}

    if name.endswith(".pdf") or raw[:4] == b"%PDF":
        return _extract_pdf(raw)
    if name.endswith((".docx",)):
        return _extract_docx(raw)
    if name.endswith((".txt", ".csv")):
        return _extract_plain(raw, engine="text")
    if name.endswith((".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp", ".bmp")):
        return _extract_image(raw)

    # эвристика по magic
    if raw[:4] == b"%PDF":
        return _extract_pdf(raw)
    if raw[:2] == b"PK":
        return _extract_docx(raw)

    try:
        text = raw.decode("utf-8")
        if text.strip():
            return {"text": text, "engine": "utf-8", "pages": 1, "warnings": []}
    except UnicodeDecodeError:
        pass

    return {
        "text": "",
        "engine": "unsupported",
        "pages": 0,
        "warnings": ["Формат файла не поддерживается для автоматического распознавания"],
    }


def _read_bytes(file_obj) -> bytes:
    if hasattr(file_obj, "read"):
        pos = file_obj.tell() if hasattr(file_obj, "tell") else None
        data = file_obj.read()
        if pos is not None and hasattr(file_obj, "seek"):
            file_obj.seek(pos)
        return data
    return b""


def _extract_pdf(raw: bytes) -> dict:
    warnings: list[str] = []
    try:
        from pypdf import PdfReader
    except ImportError:
        return {
            "text": "",
            "engine": "pdf-unavailable",
            "pages": 0,
            "warnings": ["Библиотека pypdf не установлена"],
        }

    reader = PdfReader(io.BytesIO(raw))
    parts: list[str] = []
    for page in reader.pages:
        try:
            parts.append(page.extract_text() or "")
        except Exception:  # noqa: BLE001
            parts.append("")
    text = "\n".join(parts).strip()
    engine = "pypdf-text-layer"
    if not text:
        warnings.append(
            "Текстовый слой PDF пуст — возможно, это скан; загрузите JPG/PNG или установите Tesseract OCR"
        )
        ocr_text, ocr_engine = _ocr_image_bytes(raw)
        if ocr_text.strip():
            text = ocr_text
            engine = ocr_engine
    return {
        "text": text,
        "engine": engine,
        "pages": len(reader.pages),
        "warnings": warnings,
    }


def _extract_docx(raw: bytes) -> dict:
    try:
        from docx import Document
    except ImportError:
        return {
            "text": "",
            "engine": "docx-unavailable",
            "pages": 0,
            "warnings": ["python-docx не установлен"],
        }
    doc = Document(io.BytesIO(raw))
    text = "\n".join(p.text for p in doc.paragraphs if p.text).strip()
    return {"text": text, "engine": "python-docx", "pages": 1, "warnings": []}


def _extract_plain(raw: bytes, *, engine: str) -> dict:
    for enc in ("utf-8", "utf-8-sig", "cp1251"):
        try:
            return {
                "text": raw.decode(enc),
                "engine": engine,
                "pages": 1,
                "warnings": [],
            }
        except UnicodeDecodeError:
            continue
    return {"text": "", "engine": engine, "pages": 0, "warnings": ["Не удалось декодировать текст"]}


def _extract_image(raw: bytes) -> dict:
    text, engine = _ocr_image_bytes(raw)
    warnings: list[str] = []
    if not text.strip():
        warnings.append(
            "Не удалось распознать изображение. Установите Tesseract OCR (rus) или загрузите PDF с текстовым слоем."
        )
    return {"text": text, "engine": engine, "pages": 1, "warnings": warnings}


def _ocr_image_bytes(raw: bytes) -> tuple[str, str]:
    try:
        import pytesseract
        from PIL import Image
    except ImportError:
        return "", "tesseract-missing-deps"

    try:
        img = Image.open(io.BytesIO(raw))
        text = pytesseract.image_to_string(img, lang="rus+eng")
        return text.strip(), "tesseract"
    except Exception:  # noqa: BLE001 — tesseract binary may be absent
        return "", "tesseract-unavailable"
