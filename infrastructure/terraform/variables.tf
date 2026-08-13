variable "aws_region" {
  description = "AWS Region to deploy to"
  type        = string
  default     = "ap-southeast-1"
}

variable "project_name" {
  description = "Name of the project"
  type        = string
  default     = "lankalawbot"
}

variable "environment" {
  description = "Deployment environment (e.g. production, staging)"
  type        = string
  default     = "production"
}

variable "alert_email" {
  description = "Email address for CloudWatch alarms"
  type        = string
}

variable "github_repo" {
  description = "GitHub repository (owner/repo)"
  type        = string
  default     = "Sashin517/lanka-law-bot"
}

variable "github_connection_arn" {
  description = "ARN of the AWS CodeStar Connection to GitHub"
  type        = string
}
