output "alb_dns_name" {
  value = module.ecs.alb_dns_name
  description = "The DNS name of the Application Load Balancer"
}

output "ecr_backend_url" {
  value = module.ecr.backend_repository_url
  description = "The ECR repository URL for the backend"
}

output "ecr_frontend_url" {
  value = module.ecr.frontend_repository_url
  description = "The ECR repository URL for the frontend"
}
