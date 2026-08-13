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

module "apprunner" {
  source = "./modules/apprunner"
  project_name = var.project_name
  environment = var.environment
  backend_image = module.ecr.backend_repository_url
  frontend_image = module.ecr.frontend_repository_url
  instance_role_arn = module.iam.apprunner_instance_role_arn
  access_role_arn = module.iam.apprunner_ecr_access_role_arn
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
  backend_service_name = module.apprunner.backend_service_name
  frontend_service_name = module.apprunner.frontend_service_name
}

module "s3" {
  source = "./modules/s3"
  project_name = var.project_name
}

module "codepipeline" {
  source = "./modules/codepipeline"
  project_name = var.project_name
  aws_region = var.aws_region
  account_id = data.aws_caller_identity.current.account_id
  github_repo = var.github_repo
  github_connection_arn = var.github_connection_arn
  pipeline_bucket = module.s3.pipeline_bucket_id
  pipeline_bucket_arn = module.s3.pipeline_bucket_arn
  codebuild_role_arn = module.iam.codebuild_role_arn
  codepipeline_role_arn = module.iam.codepipeline_role_arn
}
