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

variable "llm_base_url" {
  description = "OpenAI-compatible base URL for the backend chat assistant. Leave empty to disable chat."
  type        = string
  default     = ""
}

variable "llm_model" {
  description = "Model name sent to the configured LLM provider."
  type        = string
  default     = "claude-sonnet-4-6"
}

variable "enable_run_code" {
  description = "Whether the chat assistant may use the run_code tool."
  type        = bool
  default     = false
}

variable "enable_run_code_sandbox" {
  description = "Whether the chat assistant may use the run_code_sandbox tool."
  type        = bool
  default     = false
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
