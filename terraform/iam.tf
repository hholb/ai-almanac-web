# Service account used by the frontend Cloud Run service
resource "google_service_account" "frontend" {
  account_id   = "monsoon-frontend"
  display_name = "Monsoon Web Frontend"
}

# Service account used by the backend Cloud Run service
resource "google_service_account" "backend" {
  account_id   = "monsoon-backend"
  display_name = "Monsoon Web Backend"
}

# Allow the frontend service account to invoke the backend Cloud Run service
resource "google_cloud_run_v2_service_iam_member" "frontend_invokes_backend" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.backend.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.frontend.email}"
}
