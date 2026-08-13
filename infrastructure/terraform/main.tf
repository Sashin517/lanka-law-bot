provider "aws" {
  region = var.aws_region
  
  default_tags {
    tags = {
      Project     = var.project_name
      Environment = var.environment
      ManagedBy   = "Terraform"
    }
  }
}

data "aws_caller_identity" "current" {}

module "ecr" {
  source = "./modules/ecr"
  project_name = var.project_name
}

module "iam" {
  source = "./modules/iam"
  project_name = var.project_name
  aws_region = var.aws_region
  account_id = data.aws_caller_identity.current.account_id
}

module "networking" {
  source = "./modules/networking"
  project_name = var.project_name
  environment = var.environment
}

module "ecs" {
  source = "./modules/ecs"
  project_name = var.project_name
  environment = var.environment
  vpc_id = module.networking.vpc_id
  public_subnet_ids = module.networking.public_subnet_ids
  alb_security_group_id = module.networking.alb_security_group_id
  ecs_tasks_security_group_id = module.networking.ecs_tasks_security_group_id
  backend_image = module.ecr.backend_repository_url
  frontend_image = module.ecr.frontend_repository_url
  task_role_arn = module.iam.ecs_task_role_arn
  execution_role_arn = module.iam.ecs_task_execution_role_arn
}

module "ssm" {
  source = "./modules/ssm"
  project_name = var.project_name
}

module "monitoring" {
  source = "./modules/monitoring"
  project_name = var.project_name
  aws_region = var.aws_region
  alert_email = var.alert_email
  ecs_cluster_name = "${var.project_name}-cluster"
}

module "s3" {
  source = "./modules/s3"
  project_name = var.project_name
}


