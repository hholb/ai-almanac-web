# ---------------------------------------------------------------------------
# Cloud Batch — ROMP compute jobs
# Terraform provisions the worker service account and permissions.
# Actual job submission happens in Python (batch_runner.py) via the
# Google Cloud Batch SDK — no job template resource needed here.
# ---------------------------------------------------------------------------

resource "google_service_account" "batch_worker" {
  account_id   = "almanac-batch-worker"
  display_name = "Almanac Batch Worker (ROMP jobs)"
}

# Read obs + model data from the data bucket
resource "google_storage_bucket_iam_member" "worker_reads_data" {
  bucket = google_storage_bucket.data.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.batch_worker.email}"
}

# Read user-uploaded obs datasets
resource "google_storage_bucket_iam_member" "worker_reads_uploads" {
  bucket = google_storage_bucket.uploads.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.batch_worker.email}"
}

# Write job outputs (NetCDF + figures)
resource "google_storage_bucket_iam_member" "worker_writes_outputs" {
  bucket = google_storage_bucket.job_outputs.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.batch_worker.email}"
}

# Allow backend to create and run Cloud Run Jobs
resource "google_project_iam_member" "backend_run_developer" {
  project = var.project_id
  role    = "roles/run.developer"
  member  = "serviceAccount:${google_service_account.backend.email}"
}

# Backend needs to be able to act as the worker SA when submitting jobs
resource "google_service_account_iam_member" "backend_acts_as_worker" {
  service_account_id = google_service_account.batch_worker.name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.backend.email}"
}

# Allow CI to deploy new image revisions to Cloud Run
resource "google_project_iam_member" "ci_run_developer" {
  project = var.project_id
  role    = "roles/run.developer"
  member  = "serviceAccount:${google_service_account.ci.email}"
}

output "batch_worker_service_account" {
  value = google_service_account.batch_worker.email
}
