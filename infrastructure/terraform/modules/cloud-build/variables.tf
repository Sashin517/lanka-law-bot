variable "project_id" { type = string }
variable "region" { type = string }
variable "repository_id" { type = string }
variable "github_owner" { type = string }
variable "github_repository" { type = string }
variable "service_account_id" { type = string }
variable "frontend_build_vars" {
  type    = map(string)
  default = {}
}
