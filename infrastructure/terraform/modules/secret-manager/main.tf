resource "google_secret_manager_secret" "this" {
  for_each  = var.secret_ids
  project   = var.project_id
  secret_id = each.value
  labels    = var.labels

  replication {
    auto {}
  }
}

# Values are intentionally excluded from Terraform state. Operators add versions
# with scripts/sync-secrets.sh after the secret containers are provisioned.
resource "google_secret_manager_secret_iam_member" "backend_access" {
  for_each  = google_secret_manager_secret.this
  project   = var.project_id
  secret_id = each.value.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${var.backend_service_account_email}"
}
