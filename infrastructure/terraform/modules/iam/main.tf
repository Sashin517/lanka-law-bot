resource "google_service_account" "backend" {
  project      = var.project_id
  account_id   = "lankalawbot-backend-sa"
  display_name = "LankaLawBot backend runtime"
}

resource "google_service_account" "frontend" {
  project      = var.project_id
  account_id   = "lankalawbot-frontend-sa"
  display_name = "LankaLawBot frontend runtime"
}

resource "google_service_account" "cloud_build" {
  project      = var.project_id
  account_id   = "lankalawbot-build-sa"
  display_name = "LankaLawBot Cloud Build deployment"
}

locals {
  build_roles = toset([
    "roles/artifactregistry.writer",
    "roles/logging.logWriter",
    "roles/run.admin",
    "roles/secretmanager.secretAccessor",
    "roles/storage.objectViewer",
  ])
}

resource "google_project_iam_member" "build" {
  for_each = local.build_roles
  project  = var.project_id
  role     = each.value
  member   = "serviceAccount:${google_service_account.cloud_build.email}"
}

resource "google_service_account_iam_member" "build_acts_as_backend" {
  service_account_id = google_service_account.backend.name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.cloud_build.email}"
}

resource "google_service_account_iam_member" "build_acts_as_frontend" {
  service_account_id = google_service_account.frontend.name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.cloud_build.email}"
}
