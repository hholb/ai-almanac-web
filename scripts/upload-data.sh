#!/usr/bin/env bash
# Upload all benchmark data to GCS and configure the backend Cloud Run service.
#
# This script is the single source of truth for production data configuration.
# It uploads both India and Ethiopia data and sets ALL relevant env vars in one
# operation so nothing gets accidentally clobbered.
#
# Usage: ./scripts/upload-data.sh [--india-only | --ethiopia-only | --env-only]
#
# Requires: gcloud CLI authenticated with sufficient permissions
#   - storage.objects.create on almanac-data-ai-almanac
#   - run.services.update on almanac-backend

set -euo pipefail

INDIA_DIR="${INDIA_DIR:-$HOME/code/ROMP/data/india}"
ETHIOPIA_DIR="${ETHIOPIA_DIR:-$HOME/code/ROMP/data/ethiopia}"
BUCKET="gs://almanac-data-ai-almanac"
SERVICE="almanac-backend"
REGION="us-central1"

UPLOAD_INDIA=true
UPLOAD_ETHIOPIA=true
UPDATE_ENV=true

for arg in "$@"; do
  case "$arg" in
    --india-only)    UPLOAD_ETHIOPIA=false ;;
    --ethiopia-only) UPLOAD_INDIA=false ;;
    --env-only)      UPLOAD_INDIA=false; UPLOAD_ETHIOPIA=false ;;
  esac
done

# ---------------------------------------------------------------------------
# India data
# ---------------------------------------------------------------------------

if $UPLOAD_INDIA; then
  if [[ ! -d "$INDIA_DIR" ]]; then
    echo "WARN: INDIA_DIR not found: $INDIA_DIR — skipping India upload"
    echo "      Override with: INDIA_DIR=/path/to/india ./scripts/upload-data.sh"
  else
    echo "==> Uploading India obs data"
    gcloud storage cp "$INDIA_DIR/imd_rainfall_data/2p0/"*.nc "$BUCKET/obs/imd-2p0/"

    echo "==> Uploading India model data"
    india_models=(aifs aifs_daily fuxi fuxi_s2s gencast graphcast ifs neuralgcm)
    for model in "${india_models[@]}"; do
      src="$INDIA_DIR/$model"
      if [[ -d "$src" ]]; then
        echo "  $model"
        gcloud storage cp "$src/"*.nc "$BUCKET/models/india/$model/"
      else
        echo "  SKIP $model (not found: $src)"
      fi
    done
  fi
fi

# ---------------------------------------------------------------------------
# Ethiopia data
# ---------------------------------------------------------------------------

if $UPLOAD_ETHIOPIA; then
  if [[ ! -d "$ETHIOPIA_DIR" ]]; then
    echo "WARN: ETHIOPIA_DIR not found: $ETHIOPIA_DIR — skipping Ethiopia upload"
    echo "      Override with: ETHIOPIA_DIR=/path/to/ethiopia ./scripts/upload-data.sh"
  else
    echo "==> Uploading Ethiopia obs data"
    gcloud storage cp "$ETHIOPIA_DIR/obs/"*.nc "$BUCKET/obs/ethiopia/"

    echo "==> Uploading Ethiopia model data"
    ethiopia_models=(aifs fuxi gencast graphcast)
    for model in "${ethiopia_models[@]}"; do
      src="$ETHIOPIA_DIR/$model"
      if [[ -d "$src" ]]; then
        echo "  $model"
        gcloud storage cp "$src/"*.nc "$BUCKET/models/ethiopia/$model/"
      else
        echo "  SKIP $model (not found: $src)"
      fi
    done
  fi
fi

# ---------------------------------------------------------------------------
# Configure the backend Cloud Run service
# Sets ALL data-related env vars in one shot. Terraform-managed vars
# (DATABASE_URL, FRONTEND_URL, secret refs, etc.) are left untouched.
# ---------------------------------------------------------------------------

if $UPDATE_ENV; then
  echo ""
  echo "==> Updating Cloud Run env vars"

  # DEMO_OBS_DATASETS: comma-separated "Display Name=gs://path[|obs_file_pattern]"
  # IMD 2p0 files are named data_{year}.nc, Ethiopia uses plain {year}.nc.
  DEMO_OBS_DATASETS="IMD India (2 deg)=gs://${BUCKET#gs://}/obs/imd-2p0|data_{}.nc,CHIRPS Ethiopia=gs://${BUCKET#gs://}/obs/ethiopia"

  gcloud run services update "$SERVICE" \
    --region="$REGION" \
    --update-env-vars "^@^\
STORAGE_BACKEND=gcs\
@JOB_RUNNER=batch\
@GCP_PROJECT=ai-almanac\
@GCP_REGION=us-central1\
@DEMO_OBS_DATASETS=${DEMO_OBS_DATASETS}\
@INDIA_AIFS_MODEL_DIR=gs://almanac-data-ai-almanac/models/india/aifs\
@INDIA_AIFS_DAILY_MODEL_DIR=gs://almanac-data-ai-almanac/models/india/aifs_daily\
@INDIA_FUXI_MODEL_DIR=gs://almanac-data-ai-almanac/models/india/fuxi\
@INDIA_FUXI_S2S_MODEL_DIR=gs://almanac-data-ai-almanac/models/india/fuxi_s2s\
@INDIA_GENCAST_MODEL_DIR=gs://almanac-data-ai-almanac/models/india/gencast\
@INDIA_GRAPHCAST_MODEL_DIR=gs://almanac-data-ai-almanac/models/india/graphcast\
@INDIA_IFS_MODEL_DIR=gs://almanac-data-ai-almanac/models/india/ifs\
@INDIA_NEURALGCM_MODEL_DIR=gs://almanac-data-ai-almanac/models/india/neuralgcm\
@ETHIOPIA_AIFS_MODEL_DIR=gs://almanac-data-ai-almanac/models/ethiopia/aifs\
@ETHIOPIA_FUXI_MODEL_DIR=gs://almanac-data-ai-almanac/models/ethiopia/fuxi\
@ETHIOPIA_GENCAST_MODEL_DIR=gs://almanac-data-ai-almanac/models/ethiopia/gencast\
@ETHIOPIA_GRAPHCAST_MODEL_DIR=gs://almanac-data-ai-almanac/models/ethiopia/graphcast"

  echo ""
  echo "==> Done. Verify:"
  echo "    curl https://api.ai-almanac.org/health"
  echo "    curl -H 'Authorization: Bearer <token>' https://api.ai-almanac.org/datasets"
  echo "    curl -H 'Authorization: Bearer <token>' https://api.ai-almanac.org/jobs/models"
fi
