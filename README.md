# AI Almanac Web Platform

Web platform for running and viewing weather forecasts and benchmarks using the latest AIWP models.

---

## Repository Structure

```
ai-almanac-web/
├── backend/                # FastAPI application
│   ├── app/
│   │   ├── main.py         # App entrypoint, CORS, lifespan
│   │   ├── auth.py         # Globus token introspection dependency
│   │   ├── config.py       # Settings (pydantic-settings, .env)
│   │   ├── database.py     # SQLite + user/dataset/job helpers
│   │   ├── routers/
│   │   │   ├── datasets.py
│   │   │   └── jobs.py
│   │   └── services/
│   │       └── docker_runner.py  # Runs ROMP container locally
│   └── pyproject.toml
└── web/                    # SvelteKit frontend
    ├── src/
    │   ├── lib/
    │   │   ├── auth.ts           # Globus SDK authorization manager
    │   │   ├── auth-store.ts     # Svelte store wrapping auth state
    │   │   ├── api.ts            # Typed fetch wrappers
    │   │   └── benchmarks.svelte.ts
    │   └── routes/
    │       ├── +page.svelte      # Home / dashboard
    │       ├── benchmarks/       # Benchmark listing
    │       ├── user/             # User profile
    │       └── callback/         # Globus OAuth2 redirect target
    ├── .env.example
    └── package.json
```

---

## Local Development Setup

### Prerequisites

- [uv](https://docs.astral.sh/uv/) (Python package manager)
- Node.js 20+ and npm
- Docker (to run the ROMP worker container)

### Backend

```bash
cd backend
uv sync
uv run uvicorn app.main:app --reload
```

The API will be available at `http://localhost:8000`. Interactive docs at `http://localhost:8000/docs`.

By default the backend runs in **stub mode** — if `GLOBUS_CLIENT_ID` is not set, the raw Bearer token value is used as the user ID. This lets you develop without Globus credentials by passing any string as the token.

To configure the backend, create `backend/.env`:

```env
# Required for real Globus auth (leave unset for stub mode)
GLOBUS_CLIENT_ID=
GLOBUS_CLIENT_SECRET=

# Optional overrides (these are the defaults)
DB_PATH=./almanac.db
UPLOAD_DIR=./uploads
JOB_OUTPUTS_DIR=./job_outputs
FRONTEND_URL=http://localhost:5173
ROMP_IMAGE=romp:latest
JOB_TIMEOUT_SECONDS=3600
CORS_ALLOW_ALL=false
```

### Frontend

```bash
cd web
npm install
cp .env.example .env   # then fill in values
npm run dev
```

The dev server will be at `http://localhost:5173`.

---

## Globus Auth Setup

The platform uses [Globus Auth](https://docs.globus.org/api/auth/) for user authentication. Both the frontend (OAuth2 PKCE flow) and the backend (token introspection) use the **same** Globus confidential app client.

### 1.A Register a Globus App for the Backend

1. Go to [developers.globus.org](https://developers.globus.org) and sign in.
2. Click **Register a new app**.
3. Under **App Type**, choose **Confidential App** (required for backend token introspection).
4. Fill in the fields:
   - **App Name**: something descriptive, e.g. `AI Almanac Backend`
   - **Required Scopes**: leave blank for now — scopes are requested dynamically by the frontend

After creation you will see:
- **Client UUID** — this is your `GLOBUS_CLIENT_ID` / `VITE_GLOBUS_CLIENT_ID`
- **Client Secret** — generate one under using the **Create Secret** button; this is your `GLOBUS_CLIENT_SECRET`
- **Api Scope** - generate one under the **Create Scope** button, name it something descriptive like `ai-almanac-api`

### 1.B Register a Globus App for the frontend
1. Go to [developers.globus.org](https://developers.globus.org) and sign in.
2. Click **Register a new app**.
3. Under **App Type**, choose **Thick Client** 
4. Fill in the fields:
   - **App Name**: something descriptive, e.g. `AI Almanac Web`
   - **Redirects**: add `http://localhost:5173/callback` (and your production URL when deploying)

After creation you will see:
- **Client UUID** — this is your `GLOBUS_CLIENT_ID` / `VITE_GLOBUS_CLIENT_ID`


### 2. Add the Backend API Scope

The frontend requests a scope tied to the backend's own client ID so that introspected tokens identify which resource server they were issued for. The scope URI follows the pattern:

```
https://auth.globus.org/scopes/<CLIENT_UUID>/api
```

This scope is automatically available for any confidential app — no additional configuration is needed. You can see it hardcoded in `web/src/lib/auth.ts`:

```typescript
scopes: "https://auth.globus.org/scopes/<CLIENT_UUID>/api",
```

Replace `<CLIENT_UUID>` with your actual Client UUID.

### 3. Configure the Frontend

Edit `web/.env`:

```env
VITE_GLOBUS_CLIENT_ID=<your-client-uuid>
VITE_GLOBUS_REDIRECT_URL=http://localhost:5173/callback
VITE_API_URL=http://localhost:8000
```

### 4. Configure the Backend

Edit `backend/.env`:

```env
GLOBUS_CLIENT_ID=<your-client-uuid>
GLOBUS_CLIENT_SECRET=<your-client-secret>
```

With these set, the backend will validate incoming Bearer tokens via the Globus Auth introspection endpoint. Users are created lazily on first successful login — no separate registration step required.

### Auth Flow Summary

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
