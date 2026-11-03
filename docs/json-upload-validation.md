# JSON/base64 and multipart evidence upload contract

The JSON route `POST /api/v1/disputes/{id}/evidence` and multipart route `POST /api/v1/disputes/{id}/upload-evidence` now apply the **same** file-type checks, and both enforce the **10 MiB decoded file size** limit. The existing JSON request field names and multipart form fields are unchanged.

## Validation and outcomes

- JSON requires all of `file_data_base64`, `file_name`, `mime_type` when any is present. Notes-only submissions remain supported.
- Base64 is ASCII-only and strictly RFC-style validated (`validate=True`); whitespace/invalid padding/nonalphabet characters are rejected. The max encoded length is checked before allocating decoded bytes, followed by a decoded-size check.
- Multipart continues streaming at 64 KiB chunks with the existing 10 MiB limit.
- Both paths inspect content signatures (JPEG, PNG, WebP, PDF), require extension ↔ signature agreement, require declared MIME ↔ signature agreement, and sanitize filenames. The integrity analyzer continues generating SHA-256/metadata reports after validation.
- Malformed base64, missing file fields, unsupported signature, extension or MIME inconsistency → `400` with FastAPI JSON `detail`; decoded file exceeding 10 MiB → `413`; empty file → `400`.
- Upload success means a file was ingested and fingerprinted; it does **not** prove authenticity or independently verify claims. PR #2 separately fixes `USER_SUBMITTED/VERIFIED` to `USER_SUBMITTED/UNVERIFIED` for newly ingested files and must be merged independently.

## Compatibility / limitations

No API fields were added or removed. Existing clients that submitted a mismatched `mime_type` or mismatched file extension will now receive an explicit `400` instead of silently accepting the discrepancy. This is intentional tightening of the contract. A client that does not know MIME should detect the type before submission rather than inventing one.

Decoded limits do not by themselves impose a total HTTP request-body limit before FastAPI parsing. A reverse proxy / ASGI request-size control is still needed for deployment. Malware scanning and deep PDF validation are not provided; signature recognition and SHA-256 cannot establish origin/authenticity.
