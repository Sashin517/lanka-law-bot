output "backend_url" {
  description = "Public Cloud Run backend URL."
  value       = module.cloud_run.backend_url
}

output "frontend_url" {
  description = "Public Cloud Run frontend URL."
  value       = module.cloud_run.frontend_url
}

output "artifact_repository" {
  description = "Artifact Registry repository path."
  value       = module.artifact_registry.repository_path
}

output "uploads_bucket" {
  description = "GCS bucket for durable user uploads."
  value       = module.storage.bucket_name
}

output "secret_ids" {
  description = "Secret resources whose values must be populated out of band."
  value       = module.secrets.secret_ids
}
