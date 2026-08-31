variable "project_id" { type = string }
variable "region" { type = string }
variable "backend_image" { type = string }
variable "frontend_image" { type = string }
variable "backend_service_account_email" { type = string }
variable "frontend_service_account_email" { type = string }
variable "backend_secret_env" { type = map(string) }
variable "backend_env_vars" {
  type    = map(string)
  default = {}
}
variable "labels" {
  type    = map(string)
  default = {}
}
