# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

### Backend
```bash
cd backend
uv sync                                        # install dependencies
uv run uvicorn app.main:app --reload --port 8000  # run dev server
uv add <package>                               # add a dependency
```

### Frontend
```bash
cd web
npm install
npm run dev          # dev server at http://localhost:5173
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
- `config.py` — All settings via pydantic-settings (reads from `.env`)
- `auth.py` — Globus token introspection dependency; stub mode when `GLOBUS_CLIENT_ID` is unset (raw Bearer token used as user ID)
- `database.py` — SQLAlchemy Core; SQLite locally, PostgreSQL in prod via `DATABASE_URL`
- `routers/datasets.py` — Dataset registration and upload URL generation
- `routers/jobs.py` — Job submission, polling, results, metrics
- `services/storage.py` — `LocalStorage` / `GCSStorage` factory switching on `STORAGE_BACKEND`
- `services/runner.py` — `DockerRunner` / `BatchRunner` factory switching on `JOB_RUNNER`

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
