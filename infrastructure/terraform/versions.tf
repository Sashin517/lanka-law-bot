terraform {
  required_version = ">= 1.6.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
  }

  # Supply bucket and prefix during init; see scripts/bootstrap-gcp.sh.
  backend "gcs" {}
}
