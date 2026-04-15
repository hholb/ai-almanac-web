#!/usr/bin/env bash
# Wrapper entrypoint for ROMP on Cloud Run.
#
# GCSFuse mounts have high latency for random-access reads. This script
# copies the obs and model data for the requested year range to local disk
# before starting ROMP, so all file I/O happens at local SSD speed.

set -euo pipefail

LOCAL=/tmp/romp_stage
START_YEAR="${ROMP_START_DATE:0:4}"
END_YEAR="${ROMP_END_DATE:0:4}"

echo "==> Staging obs data from ${ROMP_OBS_DIR} ..."
LOCAL_OBS="${LOCAL}/obs"
mkdir -p "$LOCAL_OBS"
cp -r "${ROMP_OBS_DIR}/." "$LOCAL_OBS/"
export ROMP_OBS_DIR="$LOCAL_OBS"
echo "    obs staged: $(ls "$LOCAL_OBS" | wc -l) files"

echo "==> Staging model data (${START_YEAR}–${END_YEAR}) from ${ROMP_MODEL_DIR} ..."
LOCAL_MODEL="${LOCAL}/model"
mkdir -p "$LOCAL_MODEL"
for year in $(seq "$START_YEAR" "$END_YEAR"); do
    src="${ROMP_MODEL_DIR}/${year}.nc"
    if [[ -f "$src" ]]; then
        cp "$src" "${LOCAL_MODEL}/${year}.nc"
    fi
done
export ROMP_MODEL_DIR="$LOCAL_MODEL"
echo "    model staged: $(ls "$LOCAL_MODEL" | wc -l) files"

echo "==> Staging complete. Handing off to ROMP..."
exec /app/scripts/entrypoint.sh
