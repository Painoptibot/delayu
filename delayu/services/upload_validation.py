"""Проверка загрузок файлов (#18)."""
import os

MAX_UPLOAD_BYTES = 50 * 1024 * 1024
ALLOWED_EXTENSIONS = frozenset(
    {
        ".pdf",
        ".doc",
        ".docx",
        ".xls",
        ".xlsx",
        ".jpg",
        ".jpeg",
        ".png",
        ".gif",
        ".txt",
        ".zip",
        ".xml",
        ".sig",
    }
)
BLOCKED_EXTENSIONS = frozenset({".exe", ".bat", ".cmd", ".ps1", ".js", ".vbs", ".dll", ".msi"})


def validate_upload(uploaded_file) -> tuple[bool, str]:
    if not uploaded_file:
        return False, "Файл не выбран"
    name = uploaded_file.name or ""
    ext = os.path.splitext(name)[1].lower()
    if ext in BLOCKED_EXTENSIONS:
        return False, f"Тип файла {ext} запрещён"
    if ext and ext not in ALLOWED_EXTENSIONS:
        return False, f"Тип файла {ext} не разрешён"
    size = getattr(uploaded_file, "size", 0) or 0
    if size > MAX_UPLOAD_BYTES:
        return False, "Файл превышает 50 МБ"
    return True, ""


def file_sha256(uploaded_file) -> str:
    import hashlib

    digest = hashlib.sha256()
    if hasattr(uploaded_file, "chunks"):
        for chunk in uploaded_file.chunks():
            digest.update(chunk)
        if hasattr(uploaded_file, "seek"):
            uploaded_file.seek(0)
    else:
        digest.update(uploaded_file.read())
        if hasattr(uploaded_file, "seek"):
            uploaded_file.seek(0)
    return digest.hexdigest()
