import pytest
import io
from fastapi.testclient import TestClient
from app.main import app
from app.security.file_validator import sanitize_filename, inspect_magic_bytes, MAX_UPLOAD_SIZE_BYTES
from app.models.db_models import Base, engine, init_db


@pytest.fixture(autouse=True)
def clean_db():
    Base.metadata.drop_all(bind=engine)
    init_db()
    yield


@pytest.fixture
def client():
    return TestClient(app)


def test_path_traversal_sanitization():
    """Verifies that malicious directory traversal strings are sanitized safely."""
    assert sanitize_filename("../../etc/passwd.png") == "etcpasswd.png"
    assert sanitize_filename("..\\..\\windows\\system32\\calc.exe") == "windowssystem32calc.exe"
    assert sanitize_filename("/var/tmp/safe.pdf") == "vartmpsafe.pdf"
    assert sanitize_filename("....hidden.jpg") == "hidden.jpg"


def test_magic_bytes_inspection():
    """Verifies magic byte detection for legitimate and spoofed headers."""
    # Valid PNG
    png_header = b"\x89PNG\r\n\x1a\n" + b"\x00" * 20
    assert inspect_magic_bytes(png_header) == "image/png"

    # Valid JPEG
    jpeg_header = b"\xff\xd8\xff\xe0" + b"\x00" * 20
    assert inspect_magic_bytes(jpeg_header) == "image/jpeg"

    # Spoofed text file
    fake_header = b"This is plain text pretending to be an image."
    with pytest.raises(Exception) as excinfo:
        inspect_magic_bytes(fake_header)
    assert "Invalid file format" in str(excinfo.value)


def test_case_access_tenancy_buyer_blocked_from_other_cases(client):
    """
    Verifies that a buyer cannot read or submit evidence to another user's dispute.
    Case PP-D-INR-8841 belongs to buyer 'payer_sarah_connor_99'.
    """
    # Authorized buyer
    headers_authorized = {
        "X-User-Role": "BUYER",
        "X-User-Id": "payer_sarah_connor_99"
    }
    resp1 = client.get("/api/v1/disputes/PP-D-INR-8841", headers=headers_authorized)
    assert resp1.status_code == 200

    # Unauthorized buyer attempting cross-case access
    headers_unauthorized = {
        "X-User-Role": "BUYER",
        "X-User-Id": "attacker_buyer_66"
    }
    resp2 = client.get("/api/v1/disputes/PP-D-INR-8841", headers=headers_unauthorized)
    assert resp2.status_code == 403
    assert "Access denied: Buyer" in resp2.json()["detail"]


def test_case_access_tenancy_merchant_blocked_from_other_merchants(client):
    """
    Verifies that a merchant cannot access another merchant's case.
    Case PP-D-INR-8841 belongs to seller 'merchant_cyber_dyne_retail'.
    """
    headers_unauthorized = {
        "X-User-Role": "MERCHANT",
        "X-User-Id": "merchant_unrelated_shop"
    }
    resp = client.get("/api/v1/disputes/PP-D-INR-8841", headers=headers_unauthorized)
    assert resp.status_code == 403
    assert "is not the seller on dispute" in resp.json()["detail"]


def test_invalid_role_rejected(client):
    """Verifies that unapproved roles are rejected with 400 Bad Request."""
    headers_invalid = {"X-User-Role": "SUPER_HACKER"}
    resp = client.get("/api/v1/disputes", headers=headers_invalid)
    assert resp.status_code == 400
    assert "Invalid X-User-Role" in resp.json()["detail"]


def test_upload_file_rejected_if_magic_bytes_invalid(client):
    """Verifies that an uploaded file with spoofed extension and invalid content is rejected."""
    fake_png = io.BytesIO(b"Hello world, I am actually a text file.")
    files = {"file": ("test.png", fake_png, "image/png")}
    data = {"submitter_role": "MERCHANT"}
    
    resp = client.post("/api/v1/disputes/PP-D-INR-8841/upload-evidence", files=files, data=data)
    assert resp.status_code == 400
    assert "Invalid file format" in resp.json()["detail"]


def test_upload_file_rejected_if_exceeds_size_limit(client):
    """Verifies streaming size limiter rejects files > 10MB."""
    # Create oversized bytes stream > 10MB
    oversized = io.BytesIO(b"\x89PNG\r\n\x1a\n" + b"A" * (MAX_UPLOAD_SIZE_BYTES + 1024))
    files = {"file": ("large.png", oversized, "image/png")}
    data = {"submitter_role": "MERCHANT"}

    resp = client.post("/api/v1/disputes/PP-D-INR-8841/upload-evidence", files=files, data=data)
    assert resp.status_code == 413
    assert "exceeded maximum allowed size" in resp.json()["detail"]
