output "backend_url" {
  value = module.apprunner.backend_url
  description = "The URL of the backend App Runner service"
}

output "frontend_url" {
  value = module.apprunner.frontend_url
  description = "The URL of the frontend App Runner service"
}

output "ecr_backend_url" {
  value = module.ecr.backend_repository_url
  description = "The ECR repository URL for the backend"
}

output "ecr_frontend_url" {
  value = module.ecr.frontend_repository_url
  description = "The ECR repository URL for the frontend"
}
