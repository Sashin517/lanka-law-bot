output "backend_url" {
  value = aws_apprunner_service.backend.service_url
}

output "frontend_url" {
  value = aws_apprunner_service.frontend.service_url
}

output "backend_service_name" {
  value = aws_apprunner_service.backend.service_name
}

output "frontend_service_name" {
  value = aws_apprunner_service.frontend.service_name
}
