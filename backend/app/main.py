import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .database import init_db
from .routers import datasets, jobs


@asynccontextmanager
async def lifespan(app: FastAPI):
    await asyncio.to_thread(init_db)
    Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)
    Path(settings.job_outputs_dir).mkdir(parents=True, exist_ok=True)
    yield


app = FastAPI(title="AI Almanac API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.cors_allow_all else [settings.frontend_url],
    allow_credentials=not settings.cors_allow_all,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(datasets.router)
app.include_router(jobs.router)


@app.get("/health")
async def health():
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Local file upload endpoint
#
# Accepts PUT /upload/{full_storage_key} and saves the body to disk under
# settings.upload_dir.  In production this route is replaced by GCS signed
# URLs — the client never talks to this endpoint in prod.
# ---------------------------------------------------------------------------

@app.put("/upload/{storage_key:path}", status_code=status.HTTP_200_OK)
async def local_upload(storage_key: str, request: Request):
    dest = Path(settings.upload_dir) / storage_key
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("wb") as f:
        async for chunk in request.stream():
            f.write(chunk)
    return {"stored": str(dest)}
