# AskPDF — Oracle Cloud Infrastructure (OCI) Always Free Production Deployment Guide
**Target Cost: ₹0.00 / month (100% Free Forever Tier)**  
**Frontend Deployment:** [https://askpdf-omega.vercel.app/](https://askpdf-omega.vercel.app/)  
**Target Architecture:** ARM64 (Ampere Altra / `aarch64`) on Ubuntu 22.04 LTS  

---

## 1. Oracle Cloud Always Free Eligibility & Limits

Oracle Cloud Infrastructure provides one of the most generous Always Free compute offerings in the industry:
* **Compute Shape:** `VM.Standard.A1.Flex` (Ampere Altra ARM64 processor).
* **Free Resource Allowance:** Up to **4 OCPUs** and **24 GB RAM** across all Ampere instances per account.
  * Recommended allocation for AskPDF: **2 OCPUs and 12 GB RAM** (or 4 OCPUs / 24 GB RAM if using a single VM).
* **Storage Allowance:** Up to **200 GB total Block Volume storage** across all boot and block volumes. A standard **50 GB to 100 GB boot volume** is 100% Always Free.
* **Network Egress Allowance:** **10 TB / month** outbound data transfer free.
* **Public IPv4 Address:** 1 Ephemeral or Reserved Public IPv4 is included free.

> [!IMPORTANT]
> Always verify that the "Always Free Eligible" badge is visible next to the shape, image, and volume size during instance provisioning. Never select AMD or Intel shapes with more than 1/8 OCPU, as those are capped at 1GB RAM on the free tier.

---

## 2. Step-by-Step Instance Creation (Console Walkthrough)

### Step 2.1: Log in and Navigate to Compute Instances
1. Sign in to your Oracle Cloud account at [cloud.oracle.com](https://cloud.oracle.com/).
2. Open the navigation menu (top left) &rarr; **Compute** &rarr; **Instances**.
3. Ensure your desired Home Region is selected (e.g., *Hyderabad (ap-hyderabad-1)*, *Mumbai (ap-mumbai-1)*, or *Singapore (ap-singapore-1)*).
4. Click **Create instance**.

### Step 2.2: Configure Instance Parameters
* **Name:** `askpdf-backend-prod`
* **Placement:** Select any default Availability Domain.
* **Image and Shape:**
  1. Click **Change image** &rarr; Select **Canonical Ubuntu** &rarr; Choose **Ubuntu 22.04 LTS** (or 24.04 LTS) with ARM architecture (`aarch64`).
  2. Click **Change shape** &rarr; Select **Ampere** (ARM-based processor) &rarr; Choose **`VM.Standard.A1.Flex`**.
  3. Configure resources:
     * **OCPUs:** `2`
     * **Memory (GB):** `12`
     * *(Both will display the green **Always Free Eligible** badge).*
* **Networking:**
  * Select your existing Virtual Cloud Network (VCN) or let OCI create a default public subnet.
  * Ensure **Assign a public IPv4 address** is set to **Yes**.
* **Add SSH Keys:**
  * Select **Generate a key pair for me** (and download the private key `ssh-key.key`), or paste your existing public key (`cat ~/.ssh/id_rsa.pub`).
* **Boot Volume:**
  * Keep default (50 GB) or set up to 100 GB. Leave *"Always Free Eligible"* checked.

### Step 2.3: Zero-Touch Automation (Optional Cloud-Init)
Under **Advanced options** &rarr; **Management** &rarr; **User data**:
Paste the contents of [cloud-init.yaml](file:///opt/askpdf/cloud-init.yaml).  
*If you paste cloud-init, the instance will automatically install Docker, clone the repo, configure systemd, and prepare the stack on first boot!*

Click **Create**. The instance status will change from *PROVISIONING* to *RUNNING* in about 60–90 seconds.

---

## 3. Network & Security List Configuration (Crucial)

To allow incoming traffic from Vercel to reach Caddy and FastAPI:

1. In the OCI Console, click on your instance's **Subnet** name &rarr; Click on the **Default Security List for...**.
2. Under **Ingress Rules**, click **Add Ingress Rules**:
   * **Rule 1 (HTTP - Caddy ACME challenges):**
     * Source CIDR: `0.0.0.0/0`
     * IP Protocol: `TCP`
     * Destination Port Range: `80`
   * **Rule 2 (HTTPS - Production API Traffic):**
     * Source CIDR: `0.0.0.0/0`
     * IP Protocol: `TCP`
     * Destination Port Range: `443`
3. Click **Add Ingress Rules**.

---

## 4. Host Firewall & Automated Stack Launch (SSH)

Connect to your instance via SSH:
```bash
ssh -i /path/to/ssh-key.key ubuntu@<YOUR-INSTANCE-PUBLIC-IP>
```

### Option A: If Cloud-Init was used
The project is already in `/opt/askpdf`. Simply edit `.env` and start:
```bash
cd /opt/askpdf
nano .env
```
Add your Groq API key:
```env
LLM_API_KEY=gsk_your_groq_api_key_here
DOMAIN=<YOUR-PUBLIC-IP>.sslip.io
```
Then start the stack:
```bash
sudo systemctl start askpdf.service
```

### Option B: Quick Manual Script Setup (3 minutes)
Run this single command on the Ubuntu instance:
```bash
curl -fsSL https://raw.githubusercontent.com/safalyareddy/askpdf/feature/askpdf-upgrade/scripts/setup_oci_vm.sh | bash
```
Then edit `/opt/askpdf/.env`:
```bash
cd /opt/askpdf
nano .env
```
Set your environment variables:
```env
LLM_PROVIDER=openai_compatible
LLM_BASE_URL=https://api.groq.com/openai/v1
LLM_MODEL=llama-3.3-70b-versatile
LLM_API_KEY=gsk_your_groq_api_key_here
SUPER_USER_KEY=supersecretkey
DOMAIN=<YOUR-PUBLIC-IP>.sslip.io
```
Start the service:
```bash
sudo systemctl start askpdf.service
```

Verify everything is running:
```bash
docker compose ps
curl -s http://localhost:8000/health
```

---

## 5. Automatic HTTPS via Caddy and Free Wildcard DNS

Caddy automatically obtains an official Let's Encrypt / ZeroSSL TLS certificate.  
By using free wildcard DNS services like **sslip.io** or **nip.io**, your public IP instantly maps to a valid domain without buying a domain name:
* If your OCI Public IP is `129.150.45.67`:
  * Domain: `129.150.45.67.sslip.io`
  * Backend Public HTTPS URL: `https://129.150.45.67.sslip.io`

Test the live public endpoint from your local machine:
```bash
curl -s https://<YOUR-IP>.sslip.io/health
```
Expected response:
```json
{
  "status": "healthy",
  "provider": "openai_compatible",
  "model": "llama-3.3-70b-versatile",
  "model_online": true,
  "documents_indexed": 0,
  "storage_dir": "/app/storage"
}
```

---

## 6. Connect Vercel Frontend to the OCI Backend

1. Go to your Vercel Dashboard &rarr; Project **`askpdf`** &rarr; **Settings** &rarr; **Environment Variables**.
2. Add or update the variable:
   * **Key:** `ASKPDF_API_URL`
   * **Value:** `https://<YOUR-IP>.sslip.io` (or your custom domain)
   * **Target:** Production, Preview, Development
3. Trigger a redeployment on Vercel (or push a commit) so `build.sh` injects this URL into `config.js`.
4. Open [https://askpdf-omega.vercel.app](https://askpdf-omega.vercel.app):
   * Status dot will glow green: **`OPENAI_COMPATIBLE Online (llama-3.3-70b-versatile)`**.
   * Document Management Portal at `/admin` will load without any NOT_FOUND errors.
   * Uploading a PDF will persist it permanently to `/opt/askpdf/storage/data` and ChromaDB embeddings to `/opt/askpdf/storage/db`.

---

## 7. Monthly Cost & Quota Verification (₹0 Target)

To guarantee you never incur charges:
1. In the OCI Console, search for **Cost Analysis** &rarr; Verify current spend is **$0.00 / ₹0.00**.
2. Set up an OCI Budget alert at ₹1.00 ($0.01) to receive immediate email notification if any non-free resource is accidentally created.
3. Keep the VM running continuously—Oracle Always Free allows 24/7 execution without artificial sleep or reclamation when properly configured with real workloads.
