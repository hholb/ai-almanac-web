"""
Auth dependency — validates Globus access tokens via introspection.

Stub mode: if GLOBUS_CLIENT_ID is not set, the raw token value is used
as the external user ID so the server stays usable without credentials.
"""

import asyncio
import time
from threading import Lock
from typing import Annotated

import globus_sdk
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import settings
from .database import get_db, get_or_create_user

_bearer = HTTPBearer()

_cache: dict[str, tuple[dict, float]] = {}
_cache_lock = Lock()
_TTL = 60.0  # seconds


def _introspect_sync(token: str) -> dict:
    now = time.monotonic()
    with _cache_lock:
        if token in _cache:
            result, expires_at = _cache[token]
            if now < expires_at:
                return result

    if not settings.globus_client_id:
        result = {"active": True, "sub": token, "email": None}
    else:
        client = globus_sdk.ConfidentialAppAuthClient(
            settings.globus_client_id,
            settings.globus_client_secret,
        )
        result = client.oauth2_token_introspect(token, include="identity_set").data

    with _cache_lock:
        _cache[token] = (result, time.monotonic() + _TTL)
    return result


async def current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(_bearer)],
) -> dict:
    identity = await asyncio.to_thread(_introspect_sync, credentials.credentials)

    if not identity.get("active") or not identity.get("sub"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")

    async with get_db() as conn:
        return await get_or_create_user(conn, external_id=identity["sub"], email=identity.get("email"))


CurrentUser = Annotated[dict, Depends(current_user)]
