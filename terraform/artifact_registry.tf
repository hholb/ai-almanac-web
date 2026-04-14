# ---------------------------------------------------------------------------
# Artifact Registry — remote repository proxying GHCR
# Cloud Run requires images from GCR, AR, or Docker Hub.
# This remote repo transparently proxies ghcr.io so CI stays unchanged.
#
# Image path convention:
#   us-central1-docker.pkg.dev/PROJECT/ghcr-proxy/hholb/IMAGE:TAG
# ---------------------------------------------------------------------------

resource "google_artifact_registry_repository" "images" {
  location      = var.region
  repository_id = "almanac"
  description   = "Docker images for almanac services"
  format        = "DOCKER"
}

# Allow Cloud Run service agents to pull images from this repo
resource "google_artifact_registry_repository_iam_member" "cloud_run_pull" {
  location   = var.region
  repository = google_artifact_registry_repository.images.name
  role       = "roles/artifactregistry.reader"
  member     = "serviceAccount:service-${data.google_project.project.number}@serverless-robot-prod.iam.gserviceaccount.com"
}

data "google_project" "project" {
  project_id = var.project_id
}

# Convenience locals — build AR proxy paths from ghcr_owner.
# cloud_run.tf and batch.tf reference these instead of raw var.*_image.
locals {
  ar_prefix = "${var.region}-docker.pkg.dev/${var.project_id}/almanac"

  frontend_image = var.frontend_image != "" ? var.frontend_image : "${local.ar_prefix}/almanac-frontend:latest"
  backend_image  = var.backend_image != "" ? var.backend_image : "${local.ar_prefix}/almanac-backend:latest"
  romp_image     = var.romp_image != "" ? var.romp_image : "ghcr.io/${var.ghcr_owner}/romp:latest"
}
