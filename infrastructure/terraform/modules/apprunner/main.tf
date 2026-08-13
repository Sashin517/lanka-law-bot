resource "aws_apprunner_service" "backend" {
  service_name = "${var.project_name}-backend"

  source_configuration {
    authentication_configuration {
      access_role_arn = var.access_role_arn
    }

    image_repository {
      image_identifier      = "${var.backend_image}:latest"
      image_repository_type = "ECR"

      image_configuration {
        port = "8080"
        runtime_environment_variables = {
          "PYTHONUNBUFFERED" = "1"
          "PORT"             = "8080"
          "AWS_EXECUTION_ENV" = "AppRunner"
        }
      }
    }
    auto_deployments_enabled = true
  }

  instance_configuration {
    cpu               = "1024"
    memory            = "2048"
    instance_role_arn = var.instance_role_arn
  }

  health_check_configuration {
    protocol            = "HTTP"
    path                = "/healthz"
    interval            = 10
    timeout             = 5
    healthy_threshold   = 1
    unhealthy_threshold = 3
  }

  auto_scaling_configuration_arn = aws_apprunner_auto_scaling_configuration_version.backend.arn

  tags = {
    Project     = var.project_name
    Environment = var.environment
  }
}

resource "aws_apprunner_auto_scaling_configuration_version" "backend" {
  auto_scaling_configuration_name = "${var.project_name}-backend-scaling"
  max_concurrency                 = 50
  max_size                        = 1
  min_size                        = 1
}

resource "aws_apprunner_service" "frontend" {
  service_name = "${var.project_name}-frontend"

  source_configuration {
    authentication_configuration {
      access_role_arn = var.access_role_arn
    }

    image_repository {
      image_identifier      = "${var.frontend_image}:latest"
      image_repository_type = "ECR"

      image_configuration {
        port = "3000"
        runtime_environment_variables = {
          "NEXT_PUBLIC_API_BASE_URL" = "https://${aws_apprunner_service.backend.service_url}"
        }
      }
    }
    auto_deployments_enabled = true
  }

  instance_configuration {
    cpu               = "1024"
    memory            = "2048"
    instance_role_arn = var.instance_role_arn
  }

  health_check_configuration {
    protocol            = "HTTP"
    path                = "/"
    interval            = 10
    timeout             = 5
    healthy_threshold   = 1
    unhealthy_threshold = 3
  }

  auto_scaling_configuration_arn = aws_apprunner_auto_scaling_configuration_version.frontend.arn

  tags = {
    Project     = var.project_name
    Environment = var.environment
  }
}

resource "aws_apprunner_auto_scaling_configuration_version" "frontend" {
  auto_scaling_configuration_name = "${var.project_name}-frontend-scaling"
  max_concurrency                 = 100
  max_size                        = 1
  min_size                        = 1
}
