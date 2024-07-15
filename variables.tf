variable "aws_region" {
  description = "The AWS region to deploy resources to"
  type        = string
  default     = "eu-north-1"
}

# PostGIS
variable "postgis_dbname" {
  description = "The name of the PostGIS database"
  type        = string
}

variable "postgis_username" {
  description = "The username to connect to the PostGIS database"
  type        = string
}

variable "postgis_password" {
  description = "The password to connect to the PostGIS database"
  type        = string
}

variable "postgis_host" {
  description = "The hostname of the PostGIS database"
  type        = string
}
