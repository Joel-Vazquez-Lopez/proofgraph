"""
Secure File Handling & Content Inspection Module.
Protects against path traversal, oversized uploads, and spoofed extensions.
"""

import base64
import binascii
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

EXTENSION_MIME = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".pdf": "application/pdf",
}
ALLOWED_EXTENSIONS = set(EXTENSION_MIME)
MAX_BASE64_LENGTH = 4 * ((MAX_UPLOAD_SIZE_BYTES + 2) // 3)


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


def validate_file_signature_and_metadata(
    file_bytes: bytes, filename: str, declared_mime: str
) -> Tuple[str, str]:
    """
    Shared JSON/multipart signature, file extension, and MIME validation.
    A magic-byte match is type recognition, NOT an authenticity check.
    """
    safe_name = sanitize_filename(filename)
    _, ext = os.path.splitext(safe_name.lower())
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file extension '{ext}'.",
        )

    detected_mime = inspect_magic_bytes(file_bytes[:32])
    if EXTENSION_MIME[ext] != detected_mime:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File extension does not match detected content signature.",
        )
    if not declared_mime or declared_mime.lower().strip() != detected_mime:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Declared MIME type does not match detected content signature.",
        )
    return detected_mime, safe_name


def validate_and_decode_base64_upload(
    encoded: str, filename: str, declared_mime: str
) -> Tuple[bytes, str, str]:
    """
    Strictly decode and validate the JSON evidence path before ingestion.
    Bound encoded size before decoding to limit extra memory allocation.
    """
    if not isinstance(encoded, str):
        raise HTTPException(status_code=400, detail="Evidence file must be base64 text.")
    if len(encoded) > MAX_BASE64_LENGTH:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Evidence file exceeds maximum allowed decoded size of 10 MB.",
        )
    try:
        encoded_bytes = encoded.encode("ascii")
        file_bytes = base64.b64decode(encoded_bytes, validate=True)
    except (UnicodeEncodeError, binascii.Error, ValueError):
        raise HTTPException(status_code=400, detail="Malformed base64 evidence file.")

    if not file_bytes:
        raise HTTPException(status_code=400, detail="Evidence file is empty.")
    if len(file_bytes) > MAX_UPLOAD_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Evidence file exceeds maximum allowed decoded size of 10 MB.",
        )

    detected_mime, safe_name = validate_file_signature_and_metadata(
        file_bytes, filename, declared_mime
    )
    return file_bytes, detected_mime, safe_name


async def validate_and_read_upload(upload_file: UploadFile) -> Tuple[bytes, str, str]:
    """
    Stream-validates upload size before reading entire file into memory.
    Inspects magic bytes and returns (file_bytes, verified_mime_type, safe_stored_name).
    """
    raw_filename = upload_file.filename or "unknown_file.bin"

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

    full_bytes = b"".join(chunks)
    verified_mime, safe_name = validate_file_signature_and_metadata(
        header_bytes, raw_filename, upload_file.content_type or ""
    )

    # Generate collision-free stored filename
    stored_filename = f"{uuid.uuid4().hex}_{safe_name}"
    return full_bytes, verified_mime, stored_filename
