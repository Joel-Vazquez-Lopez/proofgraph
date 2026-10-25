# Security, Privacy & Safety Architecture

**Project:** PayPal AI Dispute Investigator  
**Security Standard:** Zero-Trust Evidence Processing & Non-Autonomous Adjudication  

---

## 1. Core Safety Principles

1. **AI Is Never an Autonomous Adjudicator:**
   The AI engine is strictly prohibited from executing payments, initiating refunds, debiting merchant accounts, or finalizing PayPal dispute rulings without authenticated human authorization.

2. **Untrusted Evidence Ingestion:**
   All uploaded documents (PDFs, images, carrier scans, text notes) are treated as potentially malicious or adversarial.

3. **Prompt Injection Boundary Isolation:**
   Text from customer claims or evidence descriptions is strictly passed to LLMs inside isolated, quoted data blocks and typed JSON schemas. LLM outputs cannot directly execute tools or bypass validation.

---

## 2. Evidence Upload Security Controls

- **File-Type Magic Byte Validation:** File MIME types are verified using header bytes rather than user-supplied extensions. Supported types: `image/jpeg`, `image/png`, `image/webp`, `application/pdf`.
- **Size Enforcements:** Maximum single file size: 10 MB (aligned with PayPal's API limit). Total case bundle: 50 MB.
- **Path Traversal Prevention:** Uploaded filenames are sanitized with UUIDs and stored with random keys; original filenames are preserved in metadata only.
- **Content Security Headers:** All media endpoints serve `X-Content-Type-Options: nosniff` and `Content-Security-Policy: default-src 'none'`.

---

## 3. RBAC & Data Provenance Protection

- Roles:
  - `MERCHANT_USER`: Can view own merchant disputes, upload merchant evidence, answer NBE inquiries.
  - `BUYER_PORTAL`: Can submit buyer claim clarification and proof of unboxing/condition.
  - `DISPUTE_INVESTIGATOR`: Can view full cross-party evidence graphs, audit integrity reports, and trigger export to PayPal.
  - `AUDITOR`: Read-only access to immutable graph logs and cryptographic file hashes.

---

## 4. Cryptographic Integrity & Chain of Custody

- Every submitted evidence file is fingerprinted at intake with `SHA-256`.
- Graph nodes reference this SHA-256 hash. If an artifact is modified, the hash mismatch immediately invalidates derived observations.
- All investigation logs and state transitions are append-only.
