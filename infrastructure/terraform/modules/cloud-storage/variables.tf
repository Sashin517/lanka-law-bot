variable "project_id" { type = string }
variable "region" { type = string }
variable "bucket_name" { type = string }
variable "backend_service_account_email" { type = string }
variable "labels" {
  type    = map(string)
  default = {}
}
