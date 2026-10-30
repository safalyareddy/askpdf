# AskPDF — Security Audit & Threat Model (v2.0)

**Date:** October 30, 2026  
**Auditor:** Senior Security & RAG Engineer  
**Classification:** Internal Production Security Audit  
**Target Environment:** macOS Apple Silicon Local Host + ngrok Public Ingress  

---

## 1. Executive Summary

This security audit reviews the threat vectors, attack surfaces, implemented defenses, and operational boundaries of **AskPDF**. The application implements defense-in-depth across the ingestion pipeline, vector retrieval engine, administrative controls, and edge tunnel configuration.

All critical vulnerabilities—including timing-attack susceptibility in admin key verification, fail-open fallback keys, arbitrary file uploads, and denial-of-service via compute exhaustion—have been remediated.

---

## 2. Threat Modeling & Vulnerability Matrix

| Attack Vector | Threat Description | Severity | Current Status | Implemented Mitigation |
| :--- | :--- | :--- | :--- | :--- |
| **Admin Auth Bypass** | Attacker executes privileged operations (`/admin/upload-pdf`, `/admin/delete-pdf`) without valid credentials. | **Critical** | **VERIFIED SECURE** | Header `X-Admin-Key` enforced. Missing or empty `SUPER_USER_KEY` in environment immediately fails closed with HTTP 503. Query param authentication strictly rejected. |
| **Timing Attacks on Auth** | Attacker uses response latency differences in string equality (`==`) to deduce character-by-character admin secrets. | **High** | **VERIFIED SECURE** | Migrated comparison to `secrets.compare_digest()`, guaranteeing constant-time evaluation regardless of character match position. |
| **Path Traversal / Arbitrary Deletion** | Malicious filename (e.g., `../../etc/passwd` or `../../../app/main.py`) supplied to upload or delete endpoints to compromise server files. | **Critical** | **VERIFIED SECURE** | `sanitize_filename()` strips all path components using `os.path.basename()` and restricts characters via regex whitelist: `[^a-zA-Z0-9_.-]`. Operations strictly jailed to `PDF_DIR`. |
| **MIME / File Header Spoofing** | Attacker uploads executable binaries or shell scripts renamed with a `.pdf` extension. | **High** | **VERIFIED SECURE** | Server inspects initial 1,024 bytes for standard PDF magic byte signature (`b"%PDF"`). Non-matching files rejected with HTTP 400 before disk write. |
| **Disk Exhaustion (DoS)** | Attacker uploads gigantic multi-gigabyte files to deplete host storage and crash the operating system. | **High** | **VERIFIED SECURE** | Stream-based upload verification enforces a hard 20 MB ceiling (`MAX_UPLOAD_SIZE_BYTES`). Exceeded uploads are immediately truncated, deleted from disk, and rejected with HTTP 413. |
| **Inference Compute Flooding (DoS)** | Parallel automated queries over public ngrok tunnel exhaust Apple Silicon GPU/Metal unified memory and CPU resources. | **High** | **VERIFIED SECURE** | In-memory sliding-window rate limiting (`check_rate_limit`) restricts requests to 30 per minute per client IP, returning HTTP 429 when exceeded. |
| **Credential Persistence Leakage** | Admin keys saved in browser `localStorage` persist across browser reboots and expose tokens on shared machines. | **Medium** | **VERIFIED SECURE** | `admin.html` strictly utilizes `sessionStorage`. Credentials are automatically wiped when the browser tab is closed. |
| **Public Ollama Exposure** | Attacker accesses raw Ollama API (`/api/generate`, `/api/tags`) to execute arbitrary prompts or unauthenticated model calls. | **Critical** | **VERIFIED SECURE** | Ollama is bound exclusively to `127.0.0.1:11434`. ngrok tunnels only port 8000. Ollama is completely unreachable from the public internet. |
| **Cross-Origin Resource Sharing (CORS)** | Malicious websites submit cross-origin requests using victim credentials. | **Medium** | **VERIFIED SECURE** | CORS middleware explicitly restricts allowed methods to `["GET", "POST", "DELETE", "OPTIONS"]` and disallows unrestricted wildcard credentials. |
| **Information Disclosure / Stack Traces** | Application crashes leak internal paths, file structures, or environment variables to the client. | **Low** | **VERIFIED SECURE** | Global exception handlers catch runtime exceptions, log full traces internally, and return sanitized generic error payloads (`HTTP 500`). |

---

## 3. Verified Protections vs. Recommended Enhancements

### A. Verified Protections (Implemented & Tested)
1. **Constant-Time Verification**: `secrets.compare_digest()` verified in `tests/test_retrieval_advanced.py`.
2. **Fail-Closed Configuration**: If `SUPER_USER_KEY` is empty or matches known development placeholders, admin operations are disabled with HTTP 503.
3. **Magic Byte Inspection**: Renamed text/binary files rejected with HTTP 400 verified in `tests/test_api.py`.
4. **Path Traversal Shielding**: Filename sanitization verified against `../../` traversal payloads.
5. **Rate Limiting**: Sliding window rate limiting verified in automated unit tests.
6. **Isolated Tunneling**: ngrok configuration forwards only port 8000.

### B. Recommended Future Hardening (For Scaled Production)
1. **Redis-Backed Rate Limiting**: If deploying multiple uvicorn worker processes in a clustered container environment, migrate the in-memory rate limiter to Redis.
2. **OAuth2 / OIDC Integration**: For multi-tenant enterprise deployments, replace the single `SUPER_USER_KEY` with role-based JWT access tokens (RBAC).
3. **Automated ClamAV Virus Scanning**: Integrate stream-based ClamAV antivirus scanning for user-submitted PDFs prior to extraction.
4. **Content Security Policy (CSP)**: Add strict HTTP response headers (`Content-Security-Policy`, `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`) in production reverse proxy.
