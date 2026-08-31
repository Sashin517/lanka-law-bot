variable "project_id" {
  description = "GCP project that owns all LankaLawBot resources."
  type        = string
}

variable "region" {
  description = "GCP region for regional resources."
  type        = string
  default     = "us-central1"
}

variable "environment" {
  description = "Deployment environment label."
  type        = string
  default     = "production"

  validation {
    condition     = contains(["staging", "production"], var.environment)
    error_message = "environment must be staging or production."
  }
}

variable "backend_image" {
  description = "Initial immutable backend image URI. CD manages later revisions."
  type        = string
}

variable "frontend_image" {
  description = "Initial immutable frontend image URI. CD manages later revisions."
  type        = string
}

variable "github_owner" {
  description = "GitHub organization or account for the Cloud Build trigger."
  type        = string
}

variable "github_repository" {
  description = "GitHub repository name for the Cloud Build trigger."
  type        = string
}

variable "create_cloud_build_trigger" {
  description = "Create the GitHub-connected Cloud Build trigger."
  type        = bool
  default     = false
}

variable "alert_email" {
  description = "Email address that receives availability alerts."
  type        = string
}

variable "backend_env_vars" {
  description = "Non-sensitive environment variables for the API."
  type        = map(string)
  default     = {}
}

variable "frontend_build_vars" {
  description = "Public Firebase values injected into the frontend build."
  type        = map(string)
  default     = {}
}

variable "labels" {
  description = "Additional labels applied to supported resources."
  type        = map(string)
  default     = {}
}
