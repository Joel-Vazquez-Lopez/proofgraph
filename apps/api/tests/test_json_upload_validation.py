"""JSON and multipart evidence must follow the same byte and MIME rules."""
import base64
import hashlib
import io

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.db_models import Base, engine, init_db
from app.security.file_validator import MAX_UPLOAD_SIZE_BYTES


DISPUTE = "PP-D-INR-8841"
PDF = b"%PDF-1.4\nsynthetic fixture upload\n%%EOF"


@pytest.fixture(autouse=True)
def clean_db():
    Base.metadata.drop_all(bind=engine)
    init_db()
    yield


@pytest.fixture
def client():
    return TestClient(app)


def _json_upload(client, data=PDF, filename="invoice.pdf", mime="application/pdf", **overrides):
    payload = {
        "submitter_role": "MERCHANT",
        "file_name": filename,
        "mime_type": mime,
        "file_data_base64": base64.b64encode(data).decode("ascii"),
    }
    payload.update(overrides)
    return client.post(f"/api/v1/disputes/{DISPUTE}/evidence", json=payload)


def _multipart_upload(client, data=PDF, filename="invoice.pdf", mime="application/pdf"):
    return client.post(
        f"/api/v1/disputes/{DISPUTE}/upload-evidence",
        files={"file": (filename, io.BytesIO(data), mime)},
        data={"submitter_role": "MERCHANT"},
    )


@pytest.mark.parametrize(
    "encoded",
    ["***not base64***", "Zg", "Zg==\n", "Zg=", "日本語"],
)
def test_json_strict_base64_rejects_malformed_text(client, encoded):
    response = _json_upload(client, file_data_base64=encoded)
    assert response.status_code == 400
    assert response.json()["detail"] == "Malformed base64 evidence file."
    detail = client.get(f"/api/v1/disputes/{DISPUTE}").json()
    assert not [n for n in detail["evidence_graph"]["nodes"] if n["type"] == "EVIDENCE_ITEM"]


def test_json_oversized_decoded_payload_returns_413(client):
    data = PDF + b"X" * (MAX_UPLOAD_SIZE_BYTES - len(PDF) + 1)
    response = _json_upload(client, data=data)
    assert response.status_code == 413
    assert "10 MB" in response.json()["detail"]


def test_json_accepts_maximum_decoded_size(client):
    data = PDF + b"X" * (MAX_UPLOAD_SIZE_BYTES - len(PDF))
    response = _json_upload(client, data=data)
    assert response.status_code == 200
    assert response.json()["integrity_finding"]["file_size_bytes"] == MAX_UPLOAD_SIZE_BYTES


@pytest.mark.parametrize(
    "filename,mime,detail_fragment",
    [
        ("invoice.png", "application/pdf", "extension does not match"),
        ("invoice.pdf", "image/png", "Declared MIME type does not match"),
        ("invoice.exe", "application/pdf", "Unsupported file extension"),
    ],
)
def test_json_metadata_mismatch_rejected(client, filename, mime, detail_fragment):
    response = _json_upload(client, filename=filename, mime=mime)
    assert response.status_code == 400
    assert detail_fragment in response.json()["detail"]


@pytest.mark.parametrize("filename,mime", [
    ("invoice.png", "application/pdf"),
    ("invoice.pdf", "image/png"),
    ("invoice.exe", "application/pdf"),
])
def test_multipart_metadata_mismatch_rejected(client, filename, mime):
    response = _multipart_upload(client, filename=filename, mime=mime)
    assert response.status_code == 400


def test_json_empty_and_partial_upload_rejected(client):
    for overrides in [
        {"file_data_base64": ""},
        {"file_data_base64": None},
        {"file_name": None},
        {"mime_type": None},
    ]:
        response = _json_upload(client, **overrides)
        assert response.status_code == 400
    response = client.post(
        f"/api/v1/disputes/{DISPUTE}/evidence",
        json={"submitter_role": "MERCHANT", "file_name": "invoice.pdf"},
    )
    assert response.status_code == 400
    assert "provided together" in response.json()["detail"]


def test_json_and_multipart_valid_pdf_return_same_hash_and_mime(client):
    json_response = _json_upload(client, filename="../../invoice.pdf")
    multipart_response = _multipart_upload(client)
    assert json_response.status_code == 200
    assert multipart_response.status_code == 200
    for response in (json_response, multipart_response):
        finding = response.json()["integrity_finding"]
        assert finding["sha256_hash"] == hashlib.sha256(PDF).hexdigest()
        assert finding["mime_type"] == "application/pdf"
        assert finding["file_size_bytes"] == len(PDF)

    nodes = client.get(f"/api/v1/disputes/{DISPUTE}").json()["evidence_graph"]["nodes"]
    uploaded = [n for n in nodes if n["type"] == "EVIDENCE_ITEM"]
    assert len(uploaded) == 2
    assert all(".." not in n["content"]["file_name"] for n in uploaded)
    assert all("/" not in n["content"]["file_name"] for n in uploaded)
