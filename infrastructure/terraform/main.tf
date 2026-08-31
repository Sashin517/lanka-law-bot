provider "google" {
  project = var.project_id
  region  = var.region
}

locals {
  labels = merge(var.labels, {
    application = "lankalawbot"
    environment = var.environment
    managed_by  = "terraform"
  })

  required_apis = toset([
    "artifactregistry.googleapis.com",
    "cloudbuild.googleapis.com",
    "iam.googleapis.com",
    "iamcredentials.googleapis.com",
    "logging.googleapis.com",
    "monitoring.googleapis.com",
    "run.googleapis.com",
    "secretmanager.googleapis.com",
    "storage.googleapis.com",
  ])

  backend_secret_env = {
    GOOGLE_API_KEY                = "google-api-key"
    PINECONE_API_KEY              = "pinecone-api-key"
    OPENROUTER_API_KEY            = "openrouter-api-key"
    NEO4J_PASSWORD                = "neo4j-password"
    JINA_API_KEY                  = "jina-api-key"
    LANGSMITH_API_KEY             = "langsmith-api-key"
    POSTGRES_PASSWORD             = "neon-postgres-password"
    DATABASE_URL                  = "neon-postgres-url"
    FIREBASE_SERVICE_ACCOUNT_JSON = "firebase-sa-json"
  }
}

resource "google_project_service" "required" {
  for_each = local.required_apis

  project            = var.project_id
  service            = each.value
  disable_on_destroy = false
}

module "artifact_registry" {
  source = "./modules/artifact-registry"

  project_id = var.project_id
  region     = var.region
  labels     = local.labels

  depends_on = [google_project_service.required]
}

module "iam" {
  source = "./modules/iam"

  project_id = var.project_id

  depends_on = [google_project_service.required]
}

module "secrets" {
  source = "./modules/secret-manager"

  project_id                    = var.project_id
  secret_ids                    = toset(values(local.backend_secret_env))
  backend_service_account_email = module.iam.backend_service_account_email
  labels                        = local.labels

  depends_on = [google_project_service.required]
}

module "storage" {
  source = "./modules/cloud-storage"

  project_id                    = var.project_id
  region                        = var.region
  bucket_name                   = "${var.project_id}-lankalawbot-uploads"
  backend_service_account_email = module.iam.backend_service_account_email
  labels                        = local.labels

  depends_on = [google_project_service.required]
}

module "cloud_run" {
  source = "./modules/cloud-run"

  project_id                     = var.project_id
  region                         = var.region
  backend_image                  = var.backend_image
  frontend_image                 = var.frontend_image
  backend_service_account_email  = module.iam.backend_service_account_email
  frontend_service_account_email = module.iam.frontend_service_account_email
  backend_secret_env             = local.backend_secret_env
  backend_env_vars = merge({
    POSTGRES_POOL_SIZE          = "3"
    POSTGRES_MAX_OVERFLOW       = "2"
    POSTGRES_AUTO_CREATE_SCHEMA = "false"
    POSTGRES_SSLMODE            = "require"
    RETRIEVAL_BACKEND           = "pinecone"
    CORS_INCLUDE_LOCALHOST      = "false"
    STORAGE_BACKEND             = "gcs"
    GCS_BUCKET_NAME             = module.storage.bucket_name
    LOG_LEVEL                   = "INFO"
  }, var.backend_env_vars)
  labels = local.labels

  depends_on = [module.secrets, module.storage]
}

module "monitoring" {
  source = "./modules/monitoring"

  project_id    = var.project_id
  backend_host  = trimprefix(module.cloud_run.backend_url, "https://")
  frontend_host = trimprefix(module.cloud_run.frontend_url, "https://")
  alert_email   = var.alert_email

  depends_on = [google_project_service.required]
}

module "cloud_build" {
  count  = var.create_cloud_build_trigger ? 1 : 0
  source = "./modules/cloud-build"

  project_id          = var.project_id
  region              = var.region
  repository_id       = module.artifact_registry.repository_id
  github_owner        = var.github_owner
  github_repository   = var.github_repository
  service_account_id  = module.iam.cloud_build_service_account_id
  frontend_build_vars = var.frontend_build_vars

  depends_on = [module.cloud_run, google_project_service.required]
}
