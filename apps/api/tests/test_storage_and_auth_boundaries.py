import io
import json
import hashlib
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.config import settings
from app.models.db_models import Base, engine, init_db


@pytest.fixture(autouse=True)
def clean_db():
    Base.metadata.drop_all(bind=engine)
    init_db()
    yield


@pytest.fixture
def client():
    return TestClient(app)


def test_reproduce_noop_evidence_submission_rejected(client):
    """
    Issue #23:
    An empty evidence submission with no file, no tracking, and no answers
    must be rejected with HTTP 400 instead of returning success: true.
    """
    empty_payload = {
        "submitter_role": "MERCHANT",
        "notes": "Just clicking submit with nothing",
    }
    resp = client.post("/api/v1/disputes/PP-D-INR-8841/evidence", json=empty_payload)
    assert resp.status_code == 400, f"Expected 400 Bad Request, got {resp.status_code}: {resp.text}"
    assert "No evidence payload provided" in resp.json()["detail"]


def test_reproduce_original_file_persistence_and_retrieval(client, tmp_path, monkeypatch):
    """
    Issue #23:
    Uploaded files must be durably stored and retrievable via an API endpoint,
    with matching SHA-256 and byte-for-byte exact equality.
    """
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path / "uploads"))
    
    file_content = b"\x89PNG\r\n\x1a\n" + b"REAL_PNG_PAYLOAD_EVIDENCE_SAMPLE_BYTES"
    sha256_expected = hashlib.sha256(file_content).hexdigest()
    
    files = {"file": ("receipt.png", io.BytesIO(file_content), "image/png")}
    data = {"submitter_role": "MERCHANT", "action_id": "act_merchant_listing"}
    
    upload_resp = client.post("/api/v1/disputes/PP-D-INR-8841/upload-evidence", files=files, data=data)
    assert upload_resp.status_code == 200
    upload_data = upload_resp.json()
    assert upload_data["success"] is True
    evidence_id = upload_data["evidence_id"]
    
    # Check that download endpoint exists and returns exact bytes and sha256 header
    download_resp = client.get(f"/api/v1/disputes/PP-D-INR-8841/evidence/{evidence_id}/download")
    assert download_resp.status_code == 200, f"Download failed: {download_resp.text}"
    assert download_resp.content == file_content
    assert download_resp.headers.get("x-evidence-sha256") == sha256_expected


def test_file_retrieval_integrity_tampering_detected(client, tmp_path, monkeypatch):
    """
    Issue #23:
    If bytes on disk are modified/tampered after upload, retrieval must fail with 409.
    """
    upload_dir = tmp_path / "uploads"
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(upload_dir))

    file_content = b"\x89PNG\r\n\x1a\n" + b"LEGIT_DOCUMENT_BYTES"
    files = {"file": ("receipt.png", io.BytesIO(file_content), "image/png")}
    data = {"submitter_role": "MERCHANT", "action_id": "act_merchant_listing"}

    upload_resp = client.post("/api/v1/disputes/PP-D-INR-8841/upload-evidence", files=files, data=data)
    evidence_id = upload_resp.json()["evidence_id"]

    # Locate file on disk and tamper with it
    case_upload_dir = upload_dir / "PP-D-INR-8841"
    matched_files = list(case_upload_dir.glob(f"{evidence_id}_*"))
    assert len(matched_files) == 1
    matched_files[0].write_bytes(b"\x89PNG\r\n\x1a\nTAMPERED_BYTES_REPLACED")

    download_resp = client.get(f"/api/v1/disputes/PP-D-INR-8841/evidence/{evidence_id}/download")
    assert download_resp.status_code == 409
    assert "Evidence file integrity failure" in download_resp.json()["detail"]


def test_structured_answers_persistence_and_action_link(client):
    """
    Issue #23:
    Structured answers must be accepted as valid evidence, stored in the graph,
    and linked via ANSWERS edges to the requested action.
    """
    payload = {
        "submitter_role": "MERCHANT",
        "action_id": "act_merchant_listing",
        "answers": {
            "listing_url": "https://cyberdyne.example/store/keychron",
            "dispatch_warehouse": "WA-01",
        },
        "notes": "Submitted inventory clarification answers",
    }
    resp = client.post("/api/v1/disputes/PP-D-INR-8841/evidence", json=payload)
    assert resp.status_code == 200
    res_data = resp.json()
    assert res_data["success"] is True
    assert len(res_data["nodes_created"]) >= 1

    # Verify detail shows the answers node
    detail_resp = client.get("/api/v1/disputes/PP-D-INR-8841")
    nodes = detail_resp.json()["evidence_graph"]["nodes"]
    answers_nodes = [n for n in nodes if n["type"] == "EVIDENCE_ITEM" and "answers" in n["content"]]
    assert len(answers_nodes) == 1
    assert answers_nodes[0]["content"]["answers"]["dispatch_warehouse"] == "WA-01"


def test_reproduce_non_demo_mode_denies_unauthenticated_and_spoofed_requests(client, monkeypatch):
    """
    Issue #22:
    When DEMO_MODE is False, unauthenticated requests (no auth token) and
    spoofed headers (like bare X-User-Role: REVIEWER) must be denied with 401.
    """
    monkeypatch.setattr(settings, "DEMO_MODE", False)
    monkeypatch.setattr(settings, "DEMO_AUTH_SECRET", "super-secret-key-123")
    
    # 1. No headers at all -> 401
    resp1 = client.get("/api/v1/disputes/PP-D-INR-8841")
    assert resp1.status_code == 401, f"Expected 401 for unauthenticated request in non-demo mode, got {resp1.status_code}"
    
    # 2. Forged reviewer header without authorization token -> 401
    resp2 = client.get("/api/v1/disputes/PP-D-INR-8841", headers={"X-User-Role": "REVIEWER", "X-User-Id": "attacker"})
    assert resp2.status_code == 401, f"Expected 401 for forged header, got {resp2.status_code}"

    # 3. Valid bearer token -> 200
    resp3 = client.get(
        "/api/v1/disputes/PP-D-INR-8841",
        headers={"Authorization": "Bearer super-secret-key-123"}
    )
    assert resp3.status_code == 200


def test_merchant_cannot_spoof_buyer_role(client):
    """
    Issue #22:
    An authenticated merchant cannot submit evidence with submitter_role='BUYER'.
    """
    headers = {
        "X-User-Role": "MERCHANT",
        "X-User-Id": "merchant_cyber_dyne_retail",
    }
    payload = {
        "submitter_role": "BUYER",
        "answers": {"fake": "claim"},
    }
    resp = client.post("/api/v1/disputes/PP-D-INR-8841/evidence", json=payload, headers=headers)
    assert resp.status_code == 403
    assert "Authenticated Merchant cannot submit evidence as 'BUYER'" in resp.json()["detail"]


def test_cross_merchant_cannot_download_evidence(client, tmp_path, monkeypatch):
    """
    Issue #22 & #23:
    A merchant owning another store cannot download evidence files from a dispute they do not own.
    """
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path / "uploads"))
    
    # Upload as legitimate merchant
    file_content = b"\x89PNG\r\n\x1a\nSECRET_DOC"
    files = {"file": ("secret.png", io.BytesIO(file_content), "image/png")}
    data = {"submitter_role": "MERCHANT"}
    headers_owner = {
        "X-User-Role": "MERCHANT",
        "X-User-Id": "merchant_cyber_dyne_retail",
    }
    upload_resp = client.post(
        "/api/v1/disputes/PP-D-INR-8841/upload-evidence",
        files=files,
        data=data,
        headers=headers_owner
    )
    assert upload_resp.status_code == 200
    evidence_id = upload_resp.json()["evidence_id"]

    # Other merchant tries to download
    headers_other = {
        "X-User-Role": "MERCHANT",
        "X-User-Id": "merchant_unrelated_shop",
    }
    download_resp = client.get(
        f"/api/v1/disputes/PP-D-INR-8841/evidence/{evidence_id}/download",
        headers=headers_other
    )
    assert download_resp.status_code == 403
    assert "is not the seller on dispute" in download_resp.json()["detail"]
