variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "region" {
  description = "GCP region for all resources"
  type        = string
  default     = "us-central1"
}

variable "ghcr_owner" {
  description = "GitHub user/org that owns the GHCR packages (e.g. hholb)"
  type        = string
}

# Derived image paths — resolved at plan time via locals in artifact_registry.tf
# Override these only if you push images to a different registry.
variable "frontend_image" {
  description = "Container image for the SvelteKit frontend"
  type        = string
  default     = ""
}

variable "backend_image" {
  description = "Container image for the FastAPI backend"
  type        = string
  default     = ""
}

variable "romp_image" {
  description = "ROMP worker image (used directly by Cloud Batch, not Cloud Run)"
  type        = string
  default     = ""
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

variable "custom_domain" {
  description = "Custom domain for the frontend (e.g. app.example.com or example.com). Leave empty to skip."
  type        = string
  default     = ""
}

variable "api_domain" {
  description = "Custom domain for the backend API (e.g. api.example.com). Leave empty to skip."
  type        = string
  default     = ""
}

variable "frontend_url" {
  description = "Frontend Cloud Run URL for CORS allowlist. Set after first deploy if unknown."
  type        = string
  default     = ""
}

variable "job_output_retention_days" {
  description = "Days before job output files are automatically deleted from GCS"
  type        = number
  default     = 30
}

# ---------------------------------------------------------------------------
# Job runner / data config
# ---------------------------------------------------------------------------

variable "job_runner" {
  description = "Job runner backend: 'modal' (production) or 'docker' (local dev)"
  type        = string
  default     = "modal"
}

variable "ethiopia_obs_dir" {
  description = "GCS URI for the Ethiopia obs dataset (datasets.yaml id: ethiopia)"
  type        = string
  default     = ""
}
variable "imd_2p0_obs_dir" {
  description = "GCS URI for the IMD India 2-degree obs dataset (datasets.yaml id: imd-2p0)"
  type        = string
  default     = ""
}

variable "india_aifs_model_dir" {
  type    = string
  default = ""
}
variable "india_aifs_daily_model_dir" {
  type    = string
  default = ""
}
variable "india_fuxi_model_dir" {
  type    = string
  default = ""
}
variable "india_fuxi_s2s_model_dir" {
  type    = string
  default = ""
}
variable "india_gencast_model_dir" {
  type    = string
  default = ""
}
variable "india_graphcast_model_dir" {
  type    = string
  default = ""
}
variable "india_ifs_model_dir" {
  type    = string
  default = ""
}
variable "india_neuralgcm_model_dir" {
  type    = string
  default = ""
}
variable "ethiopia_aifs_model_dir" {
  type    = string
  default = ""
}
variable "ethiopia_fuxi_model_dir" {
  type    = string
  default = ""
}
variable "ethiopia_gencast_model_dir" {
  type    = string
  default = ""
}
variable "ethiopia_graphcast_model_dir" {
  type    = string
  default = ""
}
