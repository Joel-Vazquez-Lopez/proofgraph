"""Regressions for the distinction between file ingestion and verification."""
import base64
import hashlib
import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.main import app
from app.models.db_models import Base, engine, init_db


CASE_ID = "PP-D-INR-8841"


@pytest.fixture(autouse=True)
def clean_db():
    Base.metadata.drop_all(bind=engine)
    init_db()
    yield


@pytest.fixture
def client():
    return TestClient(app)


def _evidence_node(client: TestClient, evidence_id: str):
    response = client.get(f"/api/v1/disputes/{CASE_ID}")
    assert response.status_code == 200
    matching = [
        node for node in response.json()["evidence_graph"]["nodes"]
        if node["id"] == evidence_id
    ]
    assert len(matching) == 1
    return matching[0]


def test_json_file_ingestion_does_not_verify_a_submitted_document(client):
    document = b"%PDF-1.4\n% buyer-supplied invoice\n%%EOF"
    response = client.post(
        f"/api/v1/disputes/{CASE_ID}/evidence",
        json={
            "submitter_role": "MERCHANT",
            "file_name": "invoice.pdf",
            "mime_type": "application/pdf",
            "file_data_base64": base64.b64encode(document).decode("ascii"),
        },
    )

    assert response.status_code == 200
    result = response.json()
    assert result["success"] is True
    assert result["integrity_finding"]["sha256_hash"] == hashlib.sha256(document).hexdigest()
    assert result["integrity_finding"]["integrity_status"] == "INCONCLUSIVE"

    node = _evidence_node(client, result["evidence_id"])
    assert node["origin"] == "USER_SUBMITTED"
    assert node["verification_status"] == "UNVERIFIED"
    assert node["verified_at"] is None
    assert node["metadata"]["integrity"]["sha256_hash"] == hashlib.sha256(document).hexdigest()

    report = client.get(f"/api/v1/disputes/{CASE_ID}/report")
    assert report.status_code == 200
    provenance = [
        row for row in report.json()["evidence_provenance_trail"]
        if row["node_id"] == result["evidence_id"]
    ]
    assert len(provenance) == 1
    assert provenance[0]["verification_status"] == "UNVERIFIED"


def test_multipart_file_ingestion_does_not_claim_external_verification(client):
    image = Image.new("RGB", (4, 4), color="white")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    image_bytes = buffer.getvalue()

    response = client.post(
        f"/api/v1/disputes/{CASE_ID}/upload-evidence",
        files={"file": ("delivery_photo.png", io.BytesIO(image_bytes), "image/png")},
        data={"submitter_role": "MERCHANT", "notes": "Merchant-provided delivery photo"},
    )

    assert response.status_code == 200
    result = response.json()
    assert result["success"] is True
    assert result["integrity_finding"]["sha256_hash"] == hashlib.sha256(image_bytes).hexdigest()
    assert result["integrity_finding"]["mime_type"] == "image/png"

    node = _evidence_node(client, result["evidence_id"])
    assert node["source"] == "MERCHANT_UPLOAD"
    assert node["origin"] == "USER_SUBMITTED"
    assert node["verification_status"] == "UNVERIFIED"
    assert node["verified_at"] is None
