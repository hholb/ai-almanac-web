"""
Auth dependency — validates Globus access tokens via introspection.

Stub mode: if GLOBUS_CLIENT_ID is not set, the raw token value is used
as the external user ID so the server stays usable without credentials.
"""

import asyncio
from typing import Annotated

import globus_sdk
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import text

from .config import settings
from .database import get_db, get_or_create_user

_bearer = HTTPBearer()


def _introspect_sync(token: str) -> dict:
    if not settings.globus_client_id:
        return {"active": True, "sub": token, "email": None}

    client = globus_sdk.ConfidentialAppAuthClient(
        settings.globus_client_id,
        settings.globus_client_secret,
    )
    resp = client.oauth2_token_introspect(token, include="identity_set")
    return resp.data


async def current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(_bearer)],
) -> dict:
    identity = await asyncio.to_thread(_introspect_sync, credentials.credentials)

    if not identity.get("active") or not identity.get("sub"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")

    def _get_or_create():
        with get_db() as conn:
            return get_or_create_user(conn, external_id=identity["sub"], email=identity.get("email"))

    return await asyncio.to_thread(_get_or_create)


CurrentUser = Annotated[dict, Depends(current_user)]
