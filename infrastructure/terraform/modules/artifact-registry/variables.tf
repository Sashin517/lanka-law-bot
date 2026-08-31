variable "project_id" { type = string }
variable "region" { type = string }
variable "repository_id" {
  type    = string
  default = "lankalawbot"
}
variable "labels" {
  type    = map(string)
  default = {}
}
