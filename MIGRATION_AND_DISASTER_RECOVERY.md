# AskPDF — Placement-Year Reliability & Disaster Recovery Runbook
**Coverage Period:** October 2026 &mdash; October 2027  
**Objective:** Zero document loss, continuous operation, and reproducible disaster recovery for the AskPDF platform.

---

## 1. Storage Architecture Overview

All application state is strictly decoupled from the Docker container layer and stored in `/opt/askpdf/storage` on the persistent host filesystem:
* **`/opt/askpdf/storage/data/`**: Raw uploaded PDF files.
* **`/opt/askpdf/storage/db/`**: ChromaDB SQLite database (`chroma.sqlite3`) and HNSW vector index files.
* **`/opt/askpdf/storage/db/documents_registry.json`**: Document metadata, upload timestamps, chunk counts, page counts, and sequential ordering.

Because `/opt/askpdf/storage` is mounted into the container at `/app/storage`, **rebuilding images, updating code, or restarting Docker containers will NEVER delete your documents or embeddings.**

---

## 2. Automated Daily Backup System

### Schedule & Mechanism
A system cron job triggers `/opt/askpdf/scripts/backup.sh` daily at **02:00 AM UTC**:
```bash
0 2 * * * /opt/askpdf/scripts/backup.sh >> /opt/askpdf/logs/backup.log 2>&1
```

### What Backup Does:
1. Compresses the entire `/opt/askpdf/storage` directory into a timestamped archive:
   `/opt/askpdf/backups/askpdf_backup_YYYYMMDD_HHMMSS.tar.gz`
2. Generates a cryptographic SHA-256 checksum file:
   `/opt/askpdf/backups/askpdf_backup_YYYYMMDD_HHMMSS.tar.gz.sha256`
3. Automatically prunes archives older than **30 days** to ensure the host never runs out of disk space.

### Manual Backup Trigger:
You can trigger an immediate backup at any time by running:
```bash
/opt/askpdf/scripts/backup.sh
```

---

## 3. Offsite Backup Export (Independent Storage)

To protect against unexpected VM termination or cloud provider incidents, never keep backups solely on the active VM.

### Option A: Download Latest Backup to Your Local Machine (Recommended)
From your local terminal (e.g. MacBook):
```bash
# Download the latest backup from OCI
scp -i ~/.ssh/oracle_key ubuntu@<OCI-PUBLIC-IP>:/opt/askpdf/backups/$(ssh -i ~/.ssh/oracle_key ubuntu@<OCI-PUBLIC-IP> "ls -t /opt/askpdf/backups/*.tar.gz | head -1 | xargs -n1 basename") ./
```

### Option B: Automatic Sync to Free Cloud Storage (e.g. Oracle Free Object Storage)
Oracle Always Free includes **10 GB of Object Storage free forever**:
1. Create an Always Free bucket named `askpdf-backups`.
2. Install and configure `rclone` or OCI CLI to push daily backups to the bucket:
   ```bash
   rclone copy /opt/askpdf/backups/ oci:askpdf-backups/ --include "*.tar.gz"
   ```

---

## 4. 5-Minute Verified Restoration Procedure

If you ever need to restore your database, roll back accidental document deletions, or recover from corrupted files:

1. SSH into the instance:
   ```bash
   ssh -i ~/.ssh/oracle_key ubuntu@<OCI-PUBLIC-IP>
   ```
2. List available backup snapshots:
   ```bash
   ls -lh /opt/askpdf/backups/
   ```
3. Run the automated restoration script:
   ```bash
   sudo /opt/askpdf/scripts/restore.sh /opt/askpdf/backups/askpdf_backup_20261030_120000.tar.gz
   ```
   *The script automatically verifies SHA256 integrity, stops the container safely, creates a pre-restoration rollback copy, unpacks the backup, restarts the service, and verifies the `/health` endpoint.*

---

## 5. Zero-Loss Migration to Another VPS / Provider

If you ever need to migrate AskPDF to another VPS, DigitalOcean Droplet, AWS, or local machine:

### On the Source VM:
1. Run a fresh backup:
   ```bash
   /opt/askpdf/scripts/backup.sh
   ```
2. Note the newest archive path (e.g. `/opt/askpdf/backups/askpdf_backup_latest.tar.gz`).

### On the Target VM:
1. Run the one-line setup script:
   ```bash
   curl -fsSL https://raw.githubusercontent.com/safalyareddy/askpdf/feature/askpdf-upgrade/scripts/setup_oci_vm.sh | bash
   ```
2. Copy the backup archive from the source VM to the target VM:
   ```bash
   scp ubuntu@<OLD-VM>:/opt/askpdf/backups/askpdf_backup_latest.tar.gz /opt/askpdf/backups/
   ```
3. Run restore:
   ```bash
   sudo /opt/askpdf/scripts/restore.sh /opt/askpdf/backups/askpdf_backup_latest.tar.gz
   ```
4. Copy `/opt/askpdf/.env` with your API keys.
5. Update `ASKPDF_API_URL` on Vercel to point to the new VM's domain.  
*All documents, embeddings, and chat history will be 100% restored.*

---

## 6. Monthly Health & Maintenance Protocol

Run this 30-second maintenance script on the 1st of every month:
```bash
/opt/askpdf/scripts/check_storage.sh
```

### Monthly Checklist:
* [ ] **Disk Usage:** Ensure boot volume has >20% free space.
* [ ] **Container Status:** Run `docker compose ps` &rarr; both `askpdf-backend` and `askpdf-caddy` are `Up (healthy)`.
* [ ] **Backup Status:** Verify recent `.tar.gz` files exist in `/opt/askpdf/backups/`.
* [ ] **SSL Certificate:** Check that HTTPS on your domain is valid (Caddy auto-renews Let's Encrypt certificates every 60 days).
* [ ] **Oracle Spend:** Verify billing remains at **₹0.00 / $0.00**.

---

## 7. Emergency Troubleshooting Runbook

| Symptom | Probable Cause | Immediate Remediation |
| :--- | :--- | :--- |
| **Frontend shows "Connecting..."** | Backend unreachable or Caddy stopped | Run `docker compose ps` and `docker compose logs caddy`. Verify ports 80/443 in OCI Security List. |
| **FastAPI container restarts in loop** | Invalid Groq API key or invalid .env format | Check logs: `docker compose logs --tail=100 askpdf-backend`. Test API key directly. |
| **SSL / HTTPS Connection Refused** | Host iptables blocking port 443 | Re-apply: `sudo iptables -I INPUT 6 -p tcp --dport 443 -j ACCEPT && sudo netfilter-persistent save`. |
| **"Failed to load documents" on /admin** | Super User Key mismatch or CORS blocking | Check `SUPER_USER_KEY` in `/opt/askpdf/.env`. Check browser console for CORS errors. |
| **Out of Disk Space error** | Old Docker build cache accumulated | Run `docker system prune -af --volumes=false` (does NOT delete `/app/storage`). |
