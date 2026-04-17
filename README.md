# AI Almanac Web Platform

Web platform for running and viewing weather forecast benchmarks against ground-truth observations using the latest AI weather prediction (AIWP) models.

Users select a region, event type (e.g. monsoon onset), and one or more models, then submit a benchmark run. Results include per-grid-point skill maps (MAE, FAR, miss rate) and spatial distribution statistics across configurable forecast windows.

---

## Repository Structure

```
ai-almanac-web/
├── backend/        # FastAPI application
│   └── app/
│       ├── config/         # Model registry (models.yaml) and settings
│       ├── routers/        # API route handlers (jobs, datasets, regions)
│       └── services/       # Storage, job runner, metrics, logging abstractions
├── web/            # SvelteKit frontend
│   └── src/
│       ├── lib/            # API client, auth, stores, shared components
│       └── routes/         # Page components and benchmark workflow views
├── terraform/      # GCP infrastructure (Cloud Run, Cloud SQL, GCS, Secret Manager)
├── modal/          # Modal.com job runner configuration
└── scripts/        # Deployment helpers
```

---

## Architecture

Three-layer stack with environment-variable-driven backend switching:

| Layer | Local dev | Production |
|---|---|---|
| Frontend | SvelteKit (Vite) at `localhost:5173` | Cloud Run |
| Backend | FastAPI + uvicorn at `localhost:8000` | Cloud Run |
| Database | SQLite (`almanac.db`) | Cloud SQL PostgreSQL |
| Storage | Local filesystem | Google Cloud Storage |
| Job runner | Docker (ROMP container) | Modal |

The job runner executes [ROMP](https://github.com/your-org/ROMP) — the benchmark computation engine. ROMP outputs per-grid-point NetCDF files (`spatial_metrics_*.nc`) which the backend reads to compute domain-wide statistics for the frontend.

---

## Local Development Setup

### Prerequisites

- [uv](https://docs.astral.sh/uv/) — Python package manager
- Node.js 20+ and npm
- Docker — to run the ROMP worker container locally

### Backend

```bash
cd backend
uv sync
uv run uvicorn app.main:app --reload --port 8000
```

API available at `http://localhost:8000`. Interactive docs at `http://localhost:8000/docs`.

Create `backend/.env` to configure:

```env
# Auth — leave unset to use stub mode (any Bearer token value becomes the user ID)
GLOBUS_CLIENT_ID=
GLOBUS_CLIENT_SECRET=

# Storage — defaults to local filesystem
STORAGE_BACKEND=local          # or "gcs"
UPLOAD_DIR=./uploads
JOB_OUTPUTS_DIR=./job_outputs

# Job runner — defaults to local Docker
JOB_RUNNER=docker              # or "cloudrun" or "modal"
ROMP_IMAGE=romp:latest
JOB_TIMEOUT_SECONDS=3600

# Demo observation datasets (comma-separated Name=path or Name=path|file_pattern)
DEMO_OBS_DATASETS=

# Model data directories — one per model/region combination.
# Models with an empty directory are excluded from the registry automatically.
INDIA_AIFS_MODEL_DIR=
INDIA_AIFS_DAILY_MODEL_DIR=
INDIA_IFS_MODEL_DIR=
INDIA_NEURALGCM_MODEL_DIR=
INDIA_FUXI_MODEL_DIR=
INDIA_GRAPHCAST_MODEL_DIR=
INDIA_GENCAST_MODEL_DIR=
INDIA_FUXI_S2S_MODEL_DIR=
ETHIOPIA_AIFS_MODEL_DIR=
ETHIOPIA_FUXI_MODEL_DIR=
ETHIOPIA_GRAPHCAST_MODEL_DIR=
ETHIOPIA_GENCAST_MODEL_DIR=

# Production only
DATABASE_URL=                  # PostgreSQL DSN (leave unset for SQLite)
GCS_DATA_BUCKET=
GCS_UPLOADS_BUCKET=
GCS_OUTPUTS_BUCKET=
GCP_PROJECT=
GCP_REGION=us-central1
FRONTEND_URL=http://localhost:5173
```

### Frontend

```bash
cd web
npm install
cp .env.example .env   # then fill in values
npm run dev
```

Dev server at `http://localhost:5173`.

```env
# web/.env
VITE_GLOBUS_CLIENT_ID=<thick-client-uuid>
VITE_REDIRECT_URL=http://localhost:5173/callback
VITE_API_URL=http://localhost:8000
```

---

## Globus Auth Setup

The platform uses [Globus Auth](https://docs.globus.org/api/auth/) for authentication. You need **two** Globus app registrations — one confidential app for the backend (token introspection) and one thick client for the frontend (PKCE flow).

### 1. Register the Backend App (Confidential)

1. Go to [developers.globus.org](https://developers.globus.org) and sign in.
2. Click **Register a new app** → **Confidential App**.
3. Name it (e.g. `AI Almanac Backend`). Required scopes: leave blank.
4. After creation, note the **Client UUID** and generate a **Client Secret**.
5. Click **Create Scope**, name it something like `ai-almanac-api`.

Set in `backend/.env`:
```env
GLOBUS_CLIENT_ID=<confidential-client-uuid>
GLOBUS_CLIENT_SECRET=<client-secret>
```

### 2. Register the Frontend App (Thick Client)

1. Click **Register a new app** → **Thick Client**.
2. Name it (e.g. `AI Almanac Web`).
3. Add redirect URIs: `http://localhost:5173/callback` (and your production URL).
4. Note the **Client UUID**.

Set in `web/.env`:
```env
VITE_GLOBUS_CLIENT_ID=<thick-client-uuid>
```

### 3. Configure the Frontend Scope

The frontend requests a scope tied to the backend's client ID so tokens carry the correct audience for introspection. Update `web/src/lib/auth.ts`:

```typescript
scopes: "https://auth.globus.org/scopes/<CONFIDENTIAL_CLIENT_UUID>/api",
```

### Auth Flow

```
Browser                          Backend                    Globus Auth
  |                                |                              |
  |-- login() -------------------------------------------------------->|
  |<-- redirect to Globus login -----------------------------------|
  |-- user authenticates ----------------------------------------->|
  |<-- redirect to /callback with auth code ----------------------|
  |-- exchange code for tokens (PKCE) ---------------------------->|
  |<-- access token + refresh token ------------------------------|
  |                                |                              |
  |-- API request (Bearer token) ->|                              |
  |                                |-- introspect(token) -------->|
  |                                |<-- {active, sub, email} -----|
  |                                |-- get_or_create_user()       |
  |<-- API response ---------------|                              |
```

Users are created lazily on first successful login — no separate registration step.

---

## Adding a New Model

1. Add a `model_dir` env var field to `Settings` in `backend/app/config.py` (e.g. `india_newmodel_model_dir: str = ""`).
2. Add an entry to `backend/app/config/models.yaml` referencing that setting via `model_dir_setting`.
3. Add frontend display metadata to `web/src/lib/data/model-catalog.ts`.

Models with an empty `model_dir` at runtime are automatically excluded from the registry.

---

## Infrastructure

Terraform in `terraform/` manages GCP resources: Cloud Run services, Cloud SQL, GCS buckets, Secret Manager. See `DEVELOPMENT.md` for first-time GCP setup.
