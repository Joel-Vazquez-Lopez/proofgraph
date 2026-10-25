import io
import pytest
from PIL import Image
from packages.shared_schemas.models import IntegrityStatus
from app.services.image_integrity import EvidenceIntegrityAnalyzer


def test_image_hashing_and_consistency():
    # Create small in-memory authentic image
    img = Image.new("RGB", (100, 100), color="blue")
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    file_bytes = buf.getvalue()

    finding = EvidenceIntegrityAnalyzer.analyze_image_bytes(
        file_bytes=file_bytes,
        file_name="receipt_blue.jpg",
        mime_type="image/jpeg"
    )

    assert finding.sha256_hash is not None
    assert len(finding.sha256_hash) == 64
    assert finding.file_size_bytes == len(file_bytes)
    assert finding.integrity_status in (IntegrityStatus.CONSISTENT, IntegrityStatus.INCONCLUSIVE)
    assert "probabilistic" in finding.probabilistic_uncertainty_note.lower()


def test_pdf_or_binary_fallback():
    binary_data = b"%PDF-1.4 sample binary receipt representation"
    finding = EvidenceIntegrityAnalyzer.analyze_image_bytes(
        file_bytes=binary_data,
        file_name="invoice.pdf",
        mime_type="application/pdf"
    )

    assert finding.sha256_hash is not None
    assert finding.integrity_status == IntegrityStatus.INCONCLUSIVE
    assert "bypassed" in finding.exif_extracted.get("note", "").lower()
