#!/usr/bin/env bash
# Wrapper entrypoint for ROMP on Cloud Run.
#
# GCSFuse mounts have high latency for random-access reads. This script
# downloads obs and model data directly from GCS (bypassing FUSE) to local
# disk before starting ROMP, so all file I/O happens at local SSD speed.

set -euo pipefail

LOCAL=/tmp/romp_stage
START_YEAR="${ROMP_START_DATE:0:4}"
END_YEAR="${ROMP_END_DATE:0:4}"

# Convert a GCSFuse mount path /mnt/BUCKET/prefix -> gs://BUCKET/prefix
mount_to_gcs() { echo "gs://$(echo "$1" | cut -d/ -f3-)"; }

OBS_GCS=$(mount_to_gcs "$ROMP_OBS_DIR")
MODEL_GCS=$(mount_to_gcs "$ROMP_MODEL_DIR")

# ---------------------------------------------------------------------------
# Stage obs — download all files in the GCS prefix directly (no FUSE).
# ---------------------------------------------------------------------------
echo "==> Staging obs data from ${OBS_GCS} ..."
LOCAL_OBS="${LOCAL}/obs"
mkdir -p "$LOCAL_OBS"

python3 - "$OBS_GCS" "$LOCAL_OBS" <<'PYEOF'
import sys
from pathlib import Path
from google.cloud import storage

gcs_uri, local_dir = sys.argv[1], Path(sys.argv[2])
bucket_name, _, prefix = gcs_uri[5:].partition("/")
prefix = prefix.rstrip("/") + "/"

client = storage.Client()
for blob in client.list_blobs(bucket_name, prefix=prefix, delimiter="/"):
    name = blob.name[len(prefix):]
    if not name or name.endswith("/"):
        continue
    blob.download_to_filename(str(local_dir / name))
    print(f"  obs: {name}")
PYEOF

export ROMP_OBS_DIR="$LOCAL_OBS"
echo "    obs staged: $(ls "$LOCAL_OBS" | wc -l) files"

# ---------------------------------------------------------------------------
# Stage model — download only the needed years directly from GCS.
# ---------------------------------------------------------------------------
echo "==> Staging model data (${START_YEAR}–${END_YEAR}) from ${MODEL_GCS} ..."
LOCAL_MODEL="${LOCAL}/model"
mkdir -p "$LOCAL_MODEL"

python3 - "$MODEL_GCS" "$LOCAL_MODEL" "$START_YEAR" "$END_YEAR" <<'PYEOF'
import sys
from pathlib import Path
from google.cloud import storage

gcs_uri, local_dir, start_year, end_year = (
    sys.argv[1], Path(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4])
)
bucket_name, _, prefix = gcs_uri[5:].partition("/")
prefix = prefix.rstrip("/") + "/"

client = storage.Client()
bucket = client.bucket(bucket_name)
for year in range(start_year, end_year + 1):
    blob = bucket.blob(f"{prefix}{year}.nc")
    dest = local_dir / f"{year}.nc"
    try:
        blob.download_to_filename(str(dest))
        print(f"  model: {year}.nc")
    except Exception:
        pass  # year not present in dataset
PYEOF

export ROMP_MODEL_DIR="$LOCAL_MODEL"
echo "    model staged: $(ls "$LOCAL_MODEL" | wc -l) files"

echo "==> Staging complete. Handing off to ROMP..."
exec /app/scripts/entrypoint.sh
