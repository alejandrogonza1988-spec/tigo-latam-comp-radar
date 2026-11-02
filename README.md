# Tigo LATAM Competitive & VAS Intelligence Radar (`tigo-latam-comp-radar`)

Production-grade automated competitive intelligence and OTT/Sports VAS tracking platform covering **Tigo (Millicom)** and its direct telecom competitors across all **12 Latin American markets** (`GT`, `SV`, `HN`, `NI`, `CR`, `PA`, `CO`, `BO`, `PY`, `UY`, `EC`, `CL`).

---

## Core Architectural Guardrails

1. **Zero Hallucination & Strict Factuality (`temperature=0.0`):**
   - Uses the official `google-genai` SDK (`gemini-2.5-flash`) with `temperature=0.0`, `response_mime_type="application/json"`, and a strict Pydantic v2 `response_schema` (`LLMExtractionEnvelope`).
   - Any price, bandwidth speed, tax inclusion flag, promo duration, or VAS post-promo price not explicitly printed in the scraped DOM is returned as `None` (`null`). Exchange rates and missing prices are never estimated or inferred.
2. **100% Deterministic Diff Engine (Zero LLM Comparison):**
   - Day `T` vs Day `T-1` comparisons run purely in deterministic Python (`src/diff_engine/comparator.py`) over canonical JSON snapshots stored in SQLite or PostgreSQL (`Cloud SQL`).
   - Categorizes changes into `NEW_OFFER_LAUNCHED`, `OFFER_RETIRED`, `PRICE_CHANGE` (exact numeric & percentage diff), `SPEED_OR_HARDWARE_CHANGE`, and `VAS_PORTFOLIO_CHANGE`.
3. **Visual & Verbatim DOM Audit Trail:**
   - Every scraped URL saves a full-page screenshot (`.png`) and the raw cleaned Markdown DOM snapshot (`.md`) under `data/audit_trail/YYYY-MM-DD/<COUNTRY_ISO>/<operator>/`, linked directly inside the HTML dashboard's **Visual Evidence Modal**.

---

## Repository Structure

```text
tigo-latam-comp-radar/
├── config/
│   ├── settings.py            # Validated env vars, Gemini settings (temp=0.0), geo-proxy routing, DB URI
│   └── markets_targets.yaml   # Complete 12-market catalog (Tigo + Competitors, currencies, playbooks)
├── src/
│   ├── browser/
│   │   ├── playwright_mgr.py  # Async Playwright manager with geo-proxy routing & stealth headers
│   │   └── dom_actions.py     # Pre-scrape playbooks (Colombia Bogotá Estrato 3, regex accordion expander)
│   ├── extractor/
│   │   ├── dom_cleaner.py     # Strips scripts/SVGs/nav/footers, surfaces hidden modals, emits Markdown
│   │   ├── schemas.py         # Strict Pydantic v2 schemas for Offers, HomeSpecs, Pricing, VAS Addons
│   │   └── gemini_parser.py   # Official `google-genai` extractor (`gemini-2.5-flash`, `temperature=0.0`)
│   ├── storage/
│   │   ├── models.py          # SQLAlchemy 2.0 ORM models: `ScrapeRun`, `OfferSnapshot`, `DailyDelta`
│   │   └── repository.py      # Persistence & historical lookup of latest valid Day T-1 snapshots
│   ├── diff_engine/
│   │   └── comparator.py      # Deterministic field-by-field comparator for Home plans & VAS addons
│   └── reporting/
│       └── report_builder.py  # Single-file Interactive HTML Dashboard (Tailwind + Alpine.js) + CSV export
├── tests/
│   └── test_diff_engine.py    # Pytest suite validating price drops, speed upgrades, VAS changes & HTML report
├── main.py                    # CLI entrypoint (`--country`, `--operator`, `--segment`, `--dry-run`)
├── Dockerfile                 # Playwright Python container ready for Google Cloud Run Jobs
├── requirements.txt           # Pinned dependencies
└── README.md
```

---

## Local Setup & Execution

### 1. Create Virtual Environment & Install Dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
playwright install chromium
```

### 2. Configure Environment Variables

Create a `.env` file in the repository root:

```dotenv
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-2.5-flash
DATABASE_URL=sqlite:///data/tigo_comp_radar.db

# Optional Geo-Proxy Routing (per-country residential proxy template or country overrides)
# PROXY_SERVER_TEMPLATE=http://brd.superproxy.io:22225
# PROXY_USERNAME_TEMPLATE=brd-customer-XXXX-zone-latam-country-{country_iso_lower}
# PROXY_PASSWORD=your_proxy_password
# PROXY_URL_CO=http://co-proxy.internal:8080
```

### 3. Run the CLI

```bash
# Dry-run end-to-end simulation (seeds Day T-1 & Day T in SQLite and builds interactive HTML report)
python main.py --dry-run

# Scrape all operators in Colombia (automatically runs Bogotá + Estrato 3 playbook)
python main.py --country CO

# Scrape Home Fiber/HFC Bundles across Colombia, Guatemala, and Chile
python main.py --country CO,GT,CL --segment HOME_BUNDLES

# Scrape a specific competitor
python main.py --country CO --operator Movistar,Claro --segment HOME_BUNDLES,VAS_ENTERTAINMENT

# Full 12-market daily sweep + publish static HTTPS dashboard to docs/index.html
python main.py --publish-docs
```

Generated reports are saved in `data/reports/daily_radar_YYYY-MM-DD.html` (standalone single-file navigable HTML dashboard) alongside UTF-8 BOM CSV exports, and when `--publish-docs` is passed, published to `docs/index.html` for **GitHub Pages HTTPS** hosting (compatible with PC, Mac, iPad, and iPhone).

### 4. GitHub Pages + GitHub Actions (Daily Automated HTTPS Link)

- **Static HTTPS Hosting (`docs/index.html`):** Deployed automatically via `.github/workflows/deploy_pages.yml` on every push to `main`.
- **Automated Daily Scrape (`05:00 AM` COT/EST):** `.github/workflows/daily_radar_update.yml` runs every day at `10:00 UTC` (`05:00 AM` Colombia/Panamá), compares `Day T` vs `Day T-1` deterministically via `data/latest_snapshot.json`, updates `docs/index.html`, and redeploys GitHub Pages.
- **Required GitHub Actions Secret:** In your GitHub repository go to **Settings → Secrets and variables → Actions → New repository secret** and add:
  - `GEMINI_API_KEY`: Your Google Gemini API key (optional secrets: `PROXY_SERVER_TEMPLATE`, `PROXY_USERNAME_TEMPLATE`, `PROXY_PASSWORD`, `DATABASE_URL`).

### 5. Run Automated Tests

```bash
pytest -v tests/test_diff_engine.py
```

---

## Google Cloud Platform Deployment (Cloud Run Jobs + Cloud Scheduler)

### Architecture on GCP
- **Compute:** **Google Cloud Run Jobs** running the Playwright Python container (`Dockerfile`).
- **Database:** **Cloud SQL for PostgreSQL** (`DATABASE_URL=postgresql+pg8000://...`) or persistent **Cloud Storage FUSE** volume mounted at `/app/data` (stores `audit_trail/*.png`, `*.md`, and `reports/*.html`).
- **Secrets:** `GEMINI_API_KEY`, `DATABASE_URL`, and `PROXY_PASSWORD` stored in **Google Secret Manager**.
- **Orchestration:** **Cloud Scheduler** triggering the Cloud Run Job daily at `05:00 America/Bogota`.

### Step-by-Step `gcloud` Deployment Commands

```bash
export PROJECT_ID="millicom-comp-intel-prod"
export REGION="us-central1"
export REPO_NAME="comp-radar"
export IMAGE_URI="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO_NAME}/tigo-latam-comp-radar:latest"
export GCS_BUCKET="tigo-latam-comp-radar-artifacts"

# 1. Create Artifact Registry repository & GCS bucket for visual audit trail + HTML dashboards
gcloud artifacts repositories create "${REPO_NAME}" \
  --repository-format=docker \
  --location="${REGION}" \
  --project="${PROJECT_ID}"

gcloud storage buckets create "gs://${GCS_BUCKET}" \
  --location="${REGION}" \
  --project="${PROJECT_ID}"

# 2. Build and push container image via Cloud Build
gcloud builds submit --tag "${IMAGE_URI}" --project="${PROJECT_ID}"

# 3. Store secrets in Secret Manager
printf "%s" "${GEMINI_API_KEY}" | gcloud secrets create gemini-api-key --data-file=- --project="${PROJECT_ID}"
printf "%s" "${DATABASE_URL}"   | gcloud secrets create radar-db-url   --data-file=- --project="${PROJECT_ID}"

# 4. Create the Cloud Run Job with GCS volume mount for screenshots (.png) & HTML reports
gcloud run jobs create tigo-latam-comp-radar-daily \
  --image="${IMAGE_URI}" \
  --region="${REGION}" \
  --project="${PROJECT_ID}" \
  --cpu=4 \
  --memory=4Gi \
  --task-timeout=3600s \
  --max-retries=1 \
  --set-secrets="GEMINI_API_KEY=gemini-api-key:latest,DATABASE_URL=radar-db-url:latest" \
  --add-volume="name=radar-storage,type=cloud-storage,bucket=${GCS_BUCKET}" \
  --add-volume-mount="volume=radar-storage,mount-path=/app/data"

# 5. Schedule automated daily execution at 05:00 AM (Bogotá / Lima / Panama time)
gcloud scheduler jobs create http trigger-tigo-latam-comp-radar \
  --location="${REGION}" \
  --schedule="0 5 * * *" \
  --time-zone="America/Bogota" \
  --uri="https://${REGION}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT_ID}/jobs/tigo-latam-comp-radar-daily:run" \
  --http-method=POST \
  --oauth-service-account-email="radar-scheduler-sa@${PROJECT_ID}.iam.gserviceaccount.com" \
  --project="${PROJECT_ID}"
```
