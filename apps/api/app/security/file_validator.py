"""
Secure File Handling & Content Inspection Module.
Protects against path traversal, oversized uploads, and spoofed extensions.
"""

import os
import re
import uuid
from typing import Tuple
from fastapi import UploadFile, HTTPException, status

MAX_UPLOAD_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB limit
CHUNK_SIZE_BYTES = 64 * 1024  # 64 KB read chunks

# Magic byte signatures for authorized file types
MAGIC_SIGNATURES = {
    "image/jpeg": [b"\xff\xd8\xff"],
    "image/png": [b"\x89PNG\r\n\x1a\n"],
    "image/webp": [b"RIFF"],
    "application/pdf": [b"%PDF-"],
}

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".pdf"}


def sanitize_filename(filename: str) -> str:
    """
    Prevents path traversal and directory escape by stripping dangerous characters.
    """
    # Remove directory separators and null bytes
    clean = re.sub(r"[\\/\0]", "", filename)
    # Remove leading dots to prevent hidden files or traversal sequences
    clean = clean.lstrip(".")
    # Remove non-ascii or dangerous shell characters
    clean = re.sub(r"[^a-zA-Z0-9._-]", "_", clean)
    if not clean:
        clean = f"upload_{uuid.uuid4().hex[:8]}.bin"
    return clean


def inspect_magic_bytes(header: bytes) -> str:
    """
    Validates file content using magic byte signatures rather than user extension.
    """
    if header.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if header.startswith(b"RIFF") and len(header) >= 12 and header[8:12] == b"WEBP":
        return "image/webp"
    if header.startswith(b"%PDF-"):
        return "application/pdf"
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Invalid file format: content signature does not match allowed types (JPEG, PNG, WEBP, PDF)."
    )


async def validate_and_read_upload(upload_file: UploadFile) -> Tuple[bytes, str, str]:
    """
    Stream-validates upload size before reading entire file into memory.
    Inspects magic bytes and returns (file_bytes, verified_mime_type, safe_stored_name).
    """
    raw_filename = upload_file.filename or "unknown_file.bin"
    safe_name = sanitize_filename(raw_filename)
    _, ext = os.path.splitext(safe_name.lower())
    
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file extension '{ext}'. Allowed extensions: {list(ALLOWED_EXTENSIONS)}"
        )

    chunks = []
    total_size = 0
    header_bytes = b""

    while True:
        chunk = await upload_file.read(CHUNK_SIZE_BYTES)
        if not chunk:
            break
        total_size += len(chunk)
        if total_size > MAX_UPLOAD_SIZE_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"Upload exceeded maximum allowed size of {MAX_UPLOAD_SIZE_BYTES // (1024 * 1024)} MB."
            )
        if len(header_bytes) < 32:
            header_bytes += chunk[:32]
        chunks.append(chunk)

    if total_size == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty (0 bytes)."
        )

    verified_mime = inspect_magic_bytes(header_bytes)
    full_bytes = b"".join(chunks)
    
    # Generate collision-free stored filename
    stored_filename = f"{uuid.uuid4().hex}_{safe_name}"
    return full_bytes, verified_mime, stored_filename
