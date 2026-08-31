output "backend_service_account_email" { value = google_service_account.backend.email }
output "frontend_service_account_email" { value = google_service_account.frontend.email }
output "cloud_build_service_account_id" { value = google_service_account.cloud_build.id }
output "cloud_build_service_account_email" { value = google_service_account.cloud_build.email }
