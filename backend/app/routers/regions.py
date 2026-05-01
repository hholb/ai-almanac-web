import json
import logging
from typing import Any

import aiohttp
from fastapi import APIRouter, HTTPException

from ..config import get_demo_datasets

router = APIRouter(prefix="/regions", tags=["regions"])
logger = logging.getLogger(__name__)

# Canonical list of regions ROMP supports. The romp_region value must match
# region_def.py exactly. This will be replaced by a DB table once the region
# schema is implemented.
KNOWN_REGIONS = [
    {
        "id": "ethiopia",
        "display_name": "Ethiopia",
        "romp_region": "Ethiopia",
        "description": "Kiremt (June–September) rainy season onset over the Ethiopian highlands.",
    },
    {
        "id": "india",
        "display_name": "India",
        "romp_region": "India",
        "description": "South-Asian summer monsoon onset using the Modified Moron–Robertson (MOK) definition.",
    },
]

REGION_BOUNDARY_ISO = {
    "ethiopia": "ETH",
    "india": "IND",
}

BOUNDARY_LEVELS = {
    "adm1": "ADM1",
    "adm2": "ADM2",
}

_BOUNDARY_CACHE: dict[tuple[str, str], dict[str, Any]] = {}


@router.get("")
def list_regions() -> list[dict]:
    """
    Return all known regions with a has_data flag indicating whether at least
    one configured obs dataset is associated with the region.
    """
    demo_names = [d["name"].lower() for d in get_demo_datasets()]
    result = []
    for region in KNOWN_REGIONS:
        name = region["display_name"].lower()
        has_data = any(name in dn for dn in demo_names)
        result.append({**region, "has_data": has_data})
    return result


def _region_iso(region: str) -> str | None:
    return REGION_BOUNDARY_ISO.get(region.strip().lower())


def _metadata_url(iso: str, boundary_type: str) -> str:
    return f"https://www.geoboundaries.org/api/current/gbOpen/{iso}/{boundary_type}/"


async def _fetch_json(session: aiohttp.ClientSession, url: str) -> dict[str, Any]:
    async with session.get(url) as response:
        body = await response.text()
        if response.status >= 400:
            raise HTTPException(
                status_code=502,
                detail=f"Boundary upstream request failed ({response.status}): {body[:300]}",
            )
        try:
            return json.loads(body)
        except json.JSONDecodeError as exc:
            raise HTTPException(
                status_code=502,
                detail=f"Boundary upstream response was not JSON: {body[:300]}",
            ) from exc


@router.get("/{region}/boundaries/{level}")
async def get_boundary(region: str, level: str) -> dict[str, Any]:
    """
    Return simplified geoBoundaries gbOpen GeoJSON for a supported benchmark region.

    The frontend cannot reliably fetch the GitHub-hosted GeoJSON directly because
    of browser CORS restrictions, so the API fetches and caches it server-side.
    """
    iso = _region_iso(region)
    if not iso:
        raise HTTPException(
            status_code=404, detail=f"No boundary mapping for region {region!r}"
        )

    boundary_type = BOUNDARY_LEVELS.get(level.strip().lower())
    if not boundary_type:
        raise HTTPException(
            status_code=404, detail=f"Unsupported boundary level {level!r}"
        )

    cache_key = (iso, boundary_type)
    cached = _BOUNDARY_CACHE.get(cache_key)
    if cached:
        return cached

    timeout = aiohttp.ClientTimeout(total=30)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        metadata = await _fetch_json(session, _metadata_url(iso, boundary_type))
        geojson_url = metadata.get("simplifiedGeometryGeoJSON") or metadata.get(
            "gjDownloadURL"
        )
        if not geojson_url:
            raise HTTPException(
                status_code=502,
                detail="geoBoundaries metadata did not include a GeoJSON URL",
            )
        geojson = await _fetch_json(session, geojson_url)

    result = {
        "metadata": {
            "boundaryID": metadata.get("boundaryID"),
            "boundaryName": metadata.get("boundaryName"),
            "boundaryType": metadata.get("boundaryType"),
            "boundarySource": metadata.get("boundarySource"),
            "boundaryLicense": metadata.get("boundaryLicense"),
            "licenseSource": metadata.get("licenseSource"),
        },
        "geojson": geojson,
    }
    _BOUNDARY_CACHE[cache_key] = result
    return result
