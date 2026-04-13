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
  description = "Container image for the SvelteKit frontend (e.g. gcr.io/PROJECT/frontend:latest)"
  type        = string
}

variable "backend_image" {
  description = "Container image for the FastAPI backend (e.g. gcr.io/PROJECT/backend:latest)"
  type        = string
}
