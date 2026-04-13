resource "google_cloud_run_v2_service" "frontend" {
  name     = "almanac-frontend"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    service_account = google_service_account.frontend.email

    containers {
      image = var.frontend_image

      ports {
        container_port = 3000
      }

      env {
        name  = "BACKEND_URL"
        value = google_cloud_run_v2_service.backend.uri
      }
    }
  }
}

resource "google_cloud_run_v2_service_iam_member" "frontend_public" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.frontend.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# ---------------------------------------------------------------------------
# Custom domain mapping for the frontend
# Uses the v1 API domain mapping which works with v2 services.
# GCP provisions a Google-managed SSL certificate automatically.
#
# After terraform apply, GCP will show the IPs/CNAME to add to your DNS:
#   gcloud beta run domain-mappings describe --domain=YOUR_DOMAIN --region=REGION
# ---------------------------------------------------------------------------
resource "google_cloud_run_domain_mapping" "frontend" {
  count    = var.custom_domain != "" ? 1 : 0
  location = var.region
  name     = var.custom_domain

  metadata {
    namespace = var.project_id
  }

  spec {
    route_name = google_cloud_run_v2_service.frontend.name
  }
}

resource "google_cloud_run_domain_mapping" "backend" {
  count    = var.api_domain != "" ? 1 : 0
  location = var.region
  name     = var.api_domain

  metadata {
    namespace = var.project_id
  }

  spec {
    route_name = google_cloud_run_v2_service.backend.name
  }
}

resource "google_cloud_run_v2_service" "backend" {
  name     = "almanac-backend"
  location = var.region
  # Frontend calls the backend directly from the browser (CORS), so it must be public.
  # App-level auth (Globus token validation) protects all non-health endpoints.
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    service_account = google_service_account.backend.email

    # Connect to Cloud SQL via built-in Auth Proxy socket
    volumes {
      name = "cloudsql"
      cloud_sql_instance {
        instances = [google_sql_database_instance.almanac.connection_name]
      }
    }

    containers {
      image = var.backend_image

      resources {
        limits = {
          cpu    = "2"
          memory = "2Gi"
        }
      }

      ports {
        container_port = 8000
      }

      volume_mounts {
        name       = "cloudsql"
        mount_path = "/cloudsql"
      }

      # Database — password injected from Secret Manager at runtime
      env {
        name  = "DATABASE_URL"
        value = "postgresql+psycopg2://almanac-backend@/almanac?host=/cloudsql/${google_sql_database_instance.almanac.connection_name}"
      }
      env {
        name = "DB_PASSWORD"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.db_password.secret_id
            version = "latest"
          }
        }
      }

      # GCS bucket names — backend uses these to build GCS paths and signed URLs
      env {
        name  = "GCS_DATA_BUCKET"
        value = google_storage_bucket.data.name
      }
      env {
        name  = "GCS_UPLOADS_BUCKET"
        value = google_storage_bucket.uploads.name
      }
      env {
        name  = "GCS_OUTPUTS_BUCKET"
        value = google_storage_bucket.job_outputs.name
      }

      # Globus auth credentials
      env {
        name = "GLOBUS_CLIENT_ID"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.globus_client_id.secret_id
            version = "latest"
          }
        }
      }
      env {
        name = "GLOBUS_CLIENT_SECRET"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.globus_client_secret.secret_id
            version = "latest"
          }
        }
      }

      # Batch worker SA — passed to batch_runner.py when submitting jobs
      env {
        name  = "BATCH_WORKER_SA"
        value = google_service_account.batch_worker.email
      }

      # Frontend origin for CORS — set var.frontend_url after first deploy
      # to lock down CORS. Leave empty to allow all origins initially.
      env {
        name  = "FRONTEND_URL"
        value = var.frontend_url
      }

      # ROMP image pulled from GHCR by Cloud Batch workers
      env {
        name  = "ROMP_IMAGE"
        value = var.romp_image
      }
    }
  }

  depends_on = [
    google_secret_manager_secret_iam_member.backend_reads_globus_id,
    google_secret_manager_secret_iam_member.backend_reads_globus_secret,
    google_secret_manager_secret_iam_member.backend_reads_db_password,
  ]
}

# Unauthenticated invocation — Globus token validation is handled at the app layer
resource "google_cloud_run_v2_service_iam_member" "backend_public" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.backend.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}
