variable "project_id" { type = string }
variable "secret_ids" { type = set(string) }
variable "backend_service_account_email" { type = string }
variable "labels" {
  type    = map(string)
  default = {}
}
