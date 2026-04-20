# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Local dev setup

The recommended dev environment uses Docker Compose. It starts a postgres container, the FastAPI backend with hot reload, and the Vite dev server.

```bash
# First time
cp .env.example backend/.env   # fill in GLOBUS_CLIENT_ID etc.
cp .env.example web/.env       # fill in VITE_GLOBUS_CLIENT_ID etc.

docker compose up --build
```

Services:
- Frontend: http://localhost:5173
- Backend: http://localhost:8000
- Postgres: localhost:5432 (user: almanac, password: almanac, db: almanac)

Source is volume-mounted into both containers so changes hot-reload without rebuilding.

The compose file automatically mounts `testdata/` and sets `DEMO_OBS_DATASETS` and `TEST_FUXI_MODEL_DIR` to point at it. This wires up the **"FuXi (Test)"** model so you can submit a full end-to-end benchmark job without any real model data. The testdata is synthetic (seeded random rainfall over a 5×5 grid, 1998–2000); regenerate it with:

```bash
uv run scripts/generate_test_data.py
```

### Running without Docker

Requires a local postgres instance with the compose credentials (or update `DATABASE_URL` in `backend/.env`).

```bash
# Backend
cd backend
uv sync
uv run uvicorn app.main:app --reload --port 8000

# Frontend
cd web
npm install
npm run dev
```

### Other frontend commands
```bash
cd web
npm run check        # type-check with svelte-check
npm run lint         # prettier check
npm run format       # prettier write
npm run build        # production build
```

## Architecture

Three-layer stack with environment-variable-driven backend switching:

| Layer | Local | Production |
|---|---|---|
| Frontend | SvelteKit (Vite dev server) | Cloud Run |
| Backend | FastAPI + uvicorn | Cloud Run |
| Database | SQLite | Cloud SQL PostgreSQL |
| Storage | Local filesystem | Google Cloud Storage |
| Job runner | Docker (ROMP container) | Cloud Batch |

### Backend (`backend/app/`)

- `main.py` — FastAPI app, CORS, lifespan hooks, local upload endpoint
- `config.py` — All settings via pydantic-settings (reads from `.env`); also exposes `get_model_registry()`, `get_metric_definitions()`, and `get_romp_defaults()` loaders
- `auth.py` — Globus token introspection dependency; stub mode when `GLOBUS_CLIENT_ID` is unset (raw Bearer token used as user ID)
- `database.py` — SQLAlchemy Core; SQLite locally, PostgreSQL in prod via `DATABASE_URL`
- `routers/config.py` — Serves `GET /config/metrics` and `GET /config/romp-defaults` from YAML (no auth required)
- `routers/datasets.py` — Dataset registration and upload URL generation
- `routers/jobs.py` — Job submission, polling, results, metrics
- `services/storage.py` — `LocalStorage` / `GCSStorage` factory switching on `STORAGE_BACKEND`
- `services/runner.py` — `DockerRunner` / `BatchRunner` factory switching on `JOB_RUNNER`

### Config files (`backend/app/config/`)

These YAML files are the single source of truth for domain configuration. Avoid hardcoding their contents anywhere else — the frontend fetches what it needs via `/config/*` endpoints.

**`models.yaml`** — Model registry. Each entry defines a model that ROMP can evaluate.

To add a model:
1. Add an entry with `id`, `display_name`, `region`, `model_type`, and the fields below.
2. Add a corresponding `<region>_<id>_model_dir` setting to `Settings` in `config.py` and expose it via an env var.
3. The model is automatically excluded at runtime if its `model_dir_setting` resolves to an empty string.

Key fields:
- `model_dir_setting` — name of the `Settings` attribute that holds the data directory path
- `probabilistic` — set `true` for ensemble models; affects which metrics ROMP computes and Cloud Run resource allocation
- `init_days` — comma-separated weekday integers (0 = Monday) when forecasts are initialised
- `start_date` / `end_date` — evaluation period; `start_year_clim` / `end_year_clim` — climatology period

**`romp.yaml`** — Metric definitions and ROMP parameter defaults.

- `metrics.deterministic` / `metrics.probabilistic` — display metadata (label, abbreviation, unit, range, `lower_is_better`, description) for every metric ROMP can produce. Add a new entry here when ROMP gains a new metric; the frontend reads this via `GET /config/metrics`.
- `defaults` — default values for every optional ROMP `env` parameter (matches `generate_config.py` in the ROMP repo). These serve as documentation and can be used to populate UI forms. Do not duplicate these defaults in frontend code.

### Frontend (`web/src/`)

- `lib/auth.ts` — Globus SDK PKCE authorization manager
- `lib/auth-store.ts` — Svelte store wrapping auth state
- `lib/api.ts` — Typed fetch wrappers for all backend endpoints
- `lib/benchmarks.svelte.ts` — Benchmark data state (Svelte 5 runes)
- `lib/components/` — UI components: `MetricMap` (OpenLayers), `ResultsViewer`, `MetricsTable`, `JobLogs`, `ComparisonPanel`, `FigureCard`, `FigureLightbox`
- `routes/benchmarks/` — Benchmark listing and detail views
- `routes/callback/` — Globus OAuth2 redirect target

### Key environment variables

Backend `.env` switches:
- `DATABASE_URL` — defaults to SQLite; set to PostgreSQL DSN for prod
- `STORAGE_BACKEND` — `local` (default) or `gcs`
- `JOB_RUNNER` — `docker` (default) or `batch`
- `GLOBUS_CLIENT_ID` / `GLOBUS_CLIENT_SECRET` — leave unset for stub auth mode
- `DEMO_OBS_DATASETS` — comma-separated `Name=path` entries shown to all users

Frontend `.env` (all `VITE_` prefix, embedded at build time):
- `VITE_GLOBUS_CLIENT_ID`, `VITE_REDIRECT_URL`, `VITE_API_URL`

## Infrastructure

Terraform in `terraform/` manages GCP resources: Cloud Run services, Cloud SQL, GCS bucket, Cloud Batch, Secret Manager. See `DEVELOPMENT.md` for first-time setup steps.
