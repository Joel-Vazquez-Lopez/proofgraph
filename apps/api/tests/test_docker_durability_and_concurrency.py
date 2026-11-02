import os
import concurrent.futures
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.config import settings
from app.models.db_models import Base, engine, init_db, SessionLocal, DisputeCaseDB
from app.services.dispute_service import DisputeService
from packages.shared_schemas.models import EvidenceSubmissionRequest


@pytest.fixture(autouse=True)
def clean_db():
    Base.metadata.drop_all(bind=engine)
    init_db()
    yield


@pytest.fixture
def client():
    return TestClient(app)


def test_capabilities_endpoint_reports_safe_boundaries(client):
    """
    Issue #27:
    Explicitly documents what is real, mocked, simulated, and not implemented.
    """
    resp = client.get("/api/v1/capabilities")
    assert resp.status_code == 200
    data = resp.json()
    
    assert data["storage"]["durable_volume_persisted"] is True
    assert data["paypal_sandbox"]["mode"] == "read_only_smoke"
    assert data["paypal_sandbox"]["live_evidence_submission_enabled"] is False
    assert data["paypal_sandbox"]["automatic_adjudication_enabled"] is False
    assert data["carrier_verification"]["independently_verified_live"] is False
    assert data["ai_engine"]["can_mutate_decisions"] is False


def test_sqlite_concurrent_writes_protection():
    """
    Issue #27:
    Validates that concurrent writes across multiple sessions do not crash
    with database locked errors thanks to WAL mode and busy timeout.
    """
    DisputeService(SessionLocal())._ensure_seed_scenarios()
    case_id = "PP-D-INR-8841"

    def submit_tracking(worker_id: int):
        with SessionLocal() as db:
            service = DisputeService(db)
            sub = EvidenceSubmissionRequest(
                submitter_role="MERCHANT",
                tracking_number=f"1Z999999999999900{worker_id}",
                carrier_name="UPS",
                notes=f"Concurrent submission worker {worker_id}",
            )
            return service.process_evidence_submission(case_id, sub)

    # Run 4 concurrent submissions in parallel threads
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(submit_tracking, i) for i in range(4)]
        results = [f.result() for f in futures]

    assert len(results) == 4
    assert all(r.success is True for r in results)


def test_docker_compose_and_next_config_integrity():
    """
    Issue #27:
    Ensures:
    1. docker-compose.yml persists SQLite in /app/storage/
    2. next.config.mjs proxies using API_INTERNAL_URL env variable
    3. apps/web/public directory exists so Docker build will not fail on COPY
    """
    repo_root = Path(__file__).resolve().parents[3]
    
    # 1. docker-compose.yml check
    compose_path = repo_root / "docker-compose.yml"
    assert compose_path.exists()
    compose_text = compose_path.read_text()
    assert "/app/storage" in compose_text
    assert "paypal_disputes.db" in compose_text

    # 2. next.config.mjs check
    next_config_path = repo_root / "apps" / "web" / "next.config.mjs"
    assert next_config_path.exists()
    next_config_text = next_config_path.read_text()
    assert "API_INTERNAL_URL" in next_config_text

    # 3. public directory check
    public_dir = repo_root / "apps" / "web" / "public"
    assert public_dir.exists(), "apps/web/public must exist for Docker build"
