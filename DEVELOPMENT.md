# Development Guide

## Architecture overview

The stack has three main pieces:

| Component | Local dev | Production |
|---|---|---|
| **Frontend** | SvelteKit dev server (`npm run dev`) | Cloud Run |
| **Backend** | FastAPI + uvicorn | Cloud Run |
| **Database** | SQLite (file on disk) | Cloud SQL PostgreSQL |
| **Storage** | Local filesystem | Google Cloud Storage |
| **Job runner** | Docker (ROMP container) | Cloud Batch |

All switching between local and production behaviour is driven by environment variables — no code changes needed.

---

## Prerequisites

- [uv](https://docs.astral.sh/uv/) — Python package manager
- [Node.js](https://nodejs.org/) 20+
- [Docker](https://docs.docker.com/get-docker/) — to run ROMP jobs locally
- The ROMP Docker image built and tagged as `romp:latest` (see ROMP repo)

---

## Backend setup

```bash
cd backend

# Copy and configure the env file
cp .env.example .env
# Edit .env — at minimum set DEMO_OBS_DATASETS and any model dirs you have locally

# Install dependencies
uv sync

# Run the dev server
uv run uvicorn app.main:app --reload --port 8000
```

The API will be available at `http://localhost:8000`. Interactive docs at `http://localhost:8000/docs`.

### Auth in development

With `GLOBUS_CLIENT_ID` left empty the server runs in **stub mode**: whatever value you pass as the Bearer token is used as the user ID. This means you can test all authenticated endpoints with any token value:

```bash
curl -H "Authorization: Bearer testuser" http://localhost:8000/datasets
```

### Running jobs locally

Jobs run as local Docker containers. Make sure `ROMP_IMAGE` in `.env` matches the tagged image you have locally (`romp:latest` by default). When you submit a job via the API, the backend fires off a `docker run` in a background thread and polls for completion.

### Adding model data

Set the relevant `*_MODEL_DIR` variables in `.env` to absolute paths on your machine. Any model without a configured directory is hidden from the UI. Example:

```
AIFS_MODEL_DIR=/data/romp/india/aifs
IFS_MODEL_DIR=/data/romp/india/ifs
```

### Adding demo datasets

`DEMO_OBS_DATASETS` is a comma-separated list of `Name=path` (or `Name=path|obs_file_pattern`) entries shown to all users:

```
DEMO_OBS_DATASETS=India Demo=/data/romp/india/obs,Ethiopia=/data/romp/ethiopia/obs|data_{}.nc
```

---

## Frontend setup

```bash
cd web
npm install
npm run dev
```

The frontend dev server proxies API requests to `http://localhost:8000` by default. Check `vite.config.ts` for proxy configuration.

---

## Environment variables reference

See `backend/.env.example` for the full list with descriptions. The key switches:

| Variable | Local default | Production value |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./almanac.db` | `postgresql+psycopg2://...` (Cloud SQL socket) |
| `STORAGE_BACKEND` | `local` | `gcs` |
| `JOB_RUNNER` | `docker` | `batch` |

---

## Project structure

```
backend/
  app/
    main.py              # FastAPI app, lifespan, local upload endpoint
    config.py            # All settings (reads from .env)
    auth.py              # Globus token validation
    database.py          # SQLAlchemy Core — SQLite or PostgreSQL
    routers/
      datasets.py        # Dataset registration and upload URLs
      jobs.py            # Job submission, results, metrics
    services/
      storage.py         # LocalStorage / GCSStorage + factory
      runner.py          # DockerRunner / BatchRunner + factory

web/
  src/
    lib/
      api.ts             # API client
      components/        # Svelte UI components

terraform/               # GCP infrastructure (Cloud Run, SQL, GCS, Batch, Secrets)
```

---

## Production deployment

### First-time setup

1. Create a GCP project and enable the required APIs:
   ```bash
   gcloud services enable \
     run.googleapis.com \
     batch.googleapis.com \
     sqladmin.googleapis.com \
     storage.googleapis.com \
     secretmanager.googleapis.com \
     cloudresourcemanager.googleapis.com
   ```

2. Create a GCS bucket for Terraform state:
   ```bash
   gcloud storage buckets create gs://YOUR_PROJECT-tf-state --location=us-central1
   ```

3. Initialize Terraform:
   ```bash
   cd terraform
   cp backend.hcl.example backend.hcl   # fill in your state bucket
   cp terraform.tfvars.example terraform.tfvars  # fill in project ID, images, etc.
   terraform init -backend-config=backend.hcl
   terraform apply
   ```

4. Populate secrets (after first `terraform apply` creates the Secret Manager resources):
   ```bash
   echo -n "YOUR_GLOBUS_CLIENT_ID"     | gcloud secrets versions add globus-client-id --data-file=-
   echo -n "YOUR_GLOBUS_CLIENT_SECRET" | gcloud secrets versions add globus-client-secret --data-file=-
   echo -n "YOUR_DB_PASSWORD"          | gcloud secrets versions add almanac-db-password --data-file=-
   ```

5. Upload model and obs data to the data bucket:
   ```bash
   gcloud storage cp -r /local/data/obs/    gs://almanac-data-YOUR_PROJECT/obs/
   gcloud storage cp -r /local/data/models/ gs://almanac-data-YOUR_PROJECT/models/
   ```

6. **Deploy the backend image first** so its Cloud Run URL is known before building the frontend:
   ```bash
   # Build and push backend
   docker build -t ghcr.io/YOUR_ORG/almanac-backend:latest ./backend
   docker push ghcr.io/YOUR_ORG/almanac-backend:latest

   # Deploy backend to Cloud Run
   gcloud run deploy almanac-backend \
     --image ghcr.io/YOUR_ORG/almanac-backend:latest \
     --region us-central1

   # Note the backend URL from the output, e.g. https://almanac-backend-abc123-uc.a.run.app
   ```

7. **Build and deploy the frontend** with the backend URL baked in:
   ```bash
   # VITE_API_URL is embedded in the JS bundle at build time
   docker build \
     --build-arg VITE_API_URL=https://almanac-backend-abc123-uc.a.run.app \
     -t ghcr.io/YOUR_ORG/almanac-frontend:latest \
     ./web
   docker push ghcr.io/YOUR_ORG/almanac-frontend:latest

   gcloud run deploy almanac-frontend \
     --image ghcr.io/YOUR_ORG/almanac-frontend:latest \
     --region us-central1
   ```

   The backend Cloud Run URL is stable — it won't change on subsequent deploys unless you delete and recreate the service. You only need to rebuild the frontend image if the backend URL changes.

### Subsequent deployments

```bash
# Backend only
docker build -t ghcr.io/YOUR_ORG/almanac-backend:latest ./backend
docker push ghcr.io/YOUR_ORG/almanac-backend:latest
gcloud run deploy almanac-backend \
  --image ghcr.io/YOUR_ORG/almanac-backend:latest \
  --region us-central1

# Frontend (rebuild if VITE_API_URL or frontend code changed)
docker build \
  --build-arg VITE_API_URL=https://almanac-backend-abc123-uc.a.run.app \
  -t ghcr.io/YOUR_ORG/almanac-frontend:latest \
  ./web
docker push ghcr.io/YOUR_ORG/almanac-frontend:latest
gcloud run deploy almanac-frontend \
  --image ghcr.io/YOUR_ORG/almanac-frontend:latest \
  --region us-central1
```

---

## Adding Python dependencies

Always use `uv add` — never edit `pyproject.toml` directly:

```bash
cd backend
uv add some-package
```
