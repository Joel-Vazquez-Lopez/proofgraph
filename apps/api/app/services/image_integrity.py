import hashlib
import io
from typing import Dict, Any, Optional
from PIL import Image, ExifTags

from packages.shared_schemas.models import (
    IntegrityStatus,
    EvidenceIntegrityFinding,
)


class EvidenceIntegrityAnalyzer:
    """
    Analyzes submitted image and document files for cryptographic provenance,
    EXIF metadata consistency, and digital alteration indicators.
    
    Adheres strictly to the safety principle:
    AI/probabilistic findings are never proof of deception and must not be used
    to reject claims or accuse parties of fraud.
    """

    ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
    KNOWN_EDITING_SIGNATURES = [
        "photoshop", "gimp", "canva", "pixlr", "midjourney", "stable diffusion", "dall-e"
    ]

    @classmethod
    def compute_sha256(cls, file_bytes: bytes) -> str:
        return hashlib.sha256(file_bytes).hexdigest()

    @classmethod
    def analyze_image_bytes(
        cls,
        file_bytes: bytes,
        file_name: str,
        mime_type: str,
        file_id: Optional[str] = None
    ) -> EvidenceIntegrityFinding:
        sha256_hash = cls.compute_sha256(file_bytes)
        file_size = len(file_bytes)
        file_id = file_id or f"file_{sha256_hash[:10]}"

        exif_data: Dict[str, Any] = {}
        has_gps = False
        software_altered = False
        editing_tools_found = []

        try:
            image = Image.open(io.BytesIO(file_bytes))
            # Verify file integrity by loading image pixels safely
            image.verify()
            
            # Reopen to read EXIF as verify() can close stream
            image = Image.open(io.BytesIO(file_bytes))
            raw_exif = image._getexif() if hasattr(image, "_getexif") and image._getexif() else {}
            
            if raw_exif:
                for tag_id, value in raw_exif.items():
                    tag_name = ExifTags.TAGS.get(tag_id, str(tag_id))
                    # Safely convert binary or non-serializable values
                    if isinstance(value, bytes):
                        value_str = value.decode("utf-8", errors="ignore").strip()
                    else:
                        value_str = str(value)

                    exif_data[tag_name] = value_str

                    if tag_name.lower() in ("software", "processingsoftware", "artist"):
                        val_lower = value_str.lower()
                        for tool in cls.KNOWN_EDITING_SIGNATURES:
                            if tool in val_lower:
                                software_altered = True
                                editing_tools_found.append(tool)

                    if tag_name == "GPSInfo":
                        has_gps = True

        except Exception as e:
            # If not a standard decodable image (e.g. PDF or text receipt), mark inconclusive
            return EvidenceIntegrityFinding(
                file_id=file_id,
                file_name=file_name,
                sha256_hash=sha256_hash,
                mime_type=mime_type,
                file_size_bytes=file_size,
                integrity_status=IntegrityStatus.INCONCLUSIVE,
                exif_extracted={"note": f"Standard image EXIF parsing bypassed: {str(e)}"},
                has_gps=False,
                software_altered=False,
                findings_summary="Non-image or stripped metadata file ingested with cryptographic fingerprint recorded.",
                probabilistic_uncertainty_note=(
                    "Absence of EXIF metadata is standard across messaging apps and web uploads "
                    "and does not indicate fraud."
                )
            )

        # Calibrated status determination
        if software_altered:
            status = IntegrityStatus.SUSPICIOUS
            summary = (
                f"Image contains metadata traces indicating export or modification via "
                f"graphic software ({', '.join(editing_tools_found)}). Verification recommended."
            )
        elif exif_data:
            status = IntegrityStatus.CONSISTENT
            camera = exif_data.get("Model", exif_data.get("Make", "Unknown device"))
            summary = f"Authentic capture metadata detected from device: {camera}."
        else:
            status = IntegrityStatus.INCONCLUSIVE
            summary = "Image file valid; EXIF metadata was not present (likely stripped during web upload or screenshot)."

        return EvidenceIntegrityFinding(
            file_id=file_id,
            file_name=file_name,
            sha256_hash=sha256_hash,
            mime_type=mime_type,
            file_size_bytes=file_size,
            integrity_status=status,
            exif_extracted=exif_data,
            has_gps=has_gps,
            software_altered=software_altered,
            findings_summary=summary,
            probabilistic_uncertainty_note=(
                "Metadata analysis is probabilistic. Metadata stripping is common in consumer apps; "
                "this finding must not be treated as proof of deception."
            )
        )
