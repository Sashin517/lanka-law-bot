locals {
  default_substitutions = {
    _REGION           = var.region
    _ARTIFACT_REPO    = var.repository_id
    _BACKEND_SERVICE  = "lankalawbot-backend"
    _FRONTEND_SERVICE = "lankalawbot-frontend"
  }
}

resource "google_cloudbuild_trigger" "main" {
  project         = var.project_id
  name            = "lankalawbot-main-deploy"
  description     = "Build immutable images and deploy main to Cloud Run"
  filename        = "cloudbuild.yaml"
  service_account = var.service_account_id
  substitutions   = merge(local.default_substitutions, var.frontend_build_vars)

  github {
    owner = var.github_owner
    name  = var.github_repository
    push { branch = "^main$" }
  }
}
