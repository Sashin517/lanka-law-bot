terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
  backend "s3" {
    bucket         = "lankalawbot-terraform-state"
    key            = "terraform/state/terraform.tfstate"
    region         = "ap-southeast-1"
    dynamodb_table = "lankalawbot-terraform-locks"
    encrypt        = true
  }
}
