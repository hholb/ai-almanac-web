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
| Database | PostgreSQL (Docker) | Cloud SQL PostgreSQL |
| Storage | Local filesystem | Google Cloud Storage |
| Job runner | Docker (ROMP container) | Modal |

The job runner executes [ROMP](https://github.com/your-org/ROMP) — the benchmark computation engine. ROMP outputs per-grid-point NetCDF files (`spatial_metrics_*.nc`) which the backend reads to compute domain-wide statistics for the frontend.

---

## Local Development Setup

### Prerequisites

- [Docker](https://docs.docker.com/get-docker/) and Docker Compose
- [uv](https://docs.astral.sh/uv/) — Python package manager (for running scripts outside Docker)
- Node.js 20+ and npm (for running frontend tooling outside Docker)

### Recommended: Docker Compose

The easiest way to run the full stack locally. Starts a PostgreSQL instance, the FastAPI backend with hot reload, and the Vite dev server — all with source mounted for live editing.

```bash
# First time only: copy env files and fill in credentials
cp .env.example backend/.env
cp .env.example web/.env

docker compose up --build
```

Services:
- Frontend: http://localhost:5173
- Backend: http://localhost:8000 (docs at `/docs`)
- PostgreSQL: `localhost:5432` (user: `almanac`, password: `almanac`, db: `almanac`)

The compose file mounts `testdata/` and wires up a **FuXi (Test)** model so you can submit a full end-to-end benchmark without real model data. Regenerate the synthetic test data with:

```bash
uv run scripts/generate_test_data.py
```

### Without Docker

Requires a local PostgreSQL instance with the credentials above (or update `DATABASE_URL` in `backend/.env`).

```bash
# Backend
cd backend
uv sync
uv run uvicorn app.main:app --reload --port 8000

# Frontend (separate terminal)
cd web
npm install
npm run dev
```

### Environment Variables

**`backend/.env`** — key settings:

```env
# Auth — leave unset for stub mode (any Bearer token value becomes the user ID)
GLOBUS_CLIENT_ID=
GLOBUS_CLIENT_SECRET=

# Database — defaults to compose postgres; set a DSN to use a different instance
DATABASE_URL=postgresql+asyncpg://almanac:almanac@localhost:5432/almanac

# Storage — defaults to local filesystem
STORAGE_BACKEND=local          # or "gcs"
UPLOAD_DIR=./uploads
JOB_OUTPUTS_DIR=./job_outputs

# Job runner
JOB_RUNNER=docker              # or "batch"
ROMP_IMAGE=romp:latest

# Demo obs dataset dirs — pattern: {ID}_OBS_DIR (see datasets.yaml for ids)
TEST_ETHIOPIA_OBS_DIR=

# Model data directories — pattern: {REGION}_{ID}_MODEL_DIR (see models.yaml)
# Models with an empty or unset dir are excluded from the registry
INDIA_FUXI_MODEL_DIR=
INDIA_GRAPHCAST_MODEL_DIR=
# ... (see backend/.env.example for full list)

# Production only
GCS_DATA_BUCKET=
GCS_UPLOADS_BUCKET=
GCS_OUTPUTS_BUCKET=
GCP_PROJECT=
GCP_REGION=us-central1
FRONTEND_URL=http://localhost:5173
```

**`web/.env`** — all values are embedded at build time:

```env
VITE_GLOBUS_CLIENT_ID=<thick-client-uuid>
VITE_REDIRECT_URL=http://localhost:5173/callback
VITE_API_URL=http://localhost:8000
```

### Frontend Commands

```bash
cd web
npm run check    # type-check with svelte-check
npm run lint     # prettier check
npm run format   # prettier write
npm run build    # production build
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

1. Add an entry to `backend/app/config/models.yaml` with `id`, `display_name`, `region`, and other required fields.
2. Set the env var `{REGION}_{ID}_MODEL_DIR` to the data directory path (local path or GCS URI).

No changes to `config.py` are needed. Models with an unset or empty env var are automatically excluded from the registry.

---

## Infrastructure

Terraform in `terraform/` manages GCP resources: Cloud Run services, Cloud SQL, GCS buckets, Secret Manager. See `DEVELOPMENT.md` for first-time GCP setup.
