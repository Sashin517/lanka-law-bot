output "repository_id" { value = google_artifact_registry_repository.this.repository_id }
output "repository_path" {
  value = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.this.repository_id}"
}
