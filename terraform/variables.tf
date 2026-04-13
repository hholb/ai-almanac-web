variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "region" {
  description = "GCP region for all resources"
  type        = string
  default     = "us-central1"
}

variable "frontend_image" {
  description = "Container image for the SvelteKit frontend"
  type        = string
}

variable "backend_image" {
  description = "Container image for the FastAPI backend"
  type        = string
}

variable "romp_image" {
  description = "ROMP worker image pulled from GHCR by Cloud Batch jobs (e.g. ghcr.io/org/romp:latest)"
  type        = string
}

variable "db_tier" {
  description = "Cloud SQL machine tier (db-f1-micro for dev, db-g1-small for prod)"
  type        = string
  default     = "db-f1-micro"
}

variable "db_password" {
  description = "Password for the almanac-backend Cloud SQL user"
  type        = string
  sensitive   = true
}

variable "job_output_retention_days" {
  description = "Days before job output files are automatically deleted from GCS"
  type        = number
  default     = 30
}
