from fastapi import APIRouter

from ..config import get_demo_datasets

router = APIRouter(prefix="/regions", tags=["regions"])

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
