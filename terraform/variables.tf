variable "project_id" {
  description = "Google Cloud Project ID"
  type        = string
  default     = "long-facet-427508-j2"
}

variable "region" {
  description = "Default Google Cloud Region"
  type        = string
  default     = "europe-west4"
}

variable "zone" {
  description = "Default Google Cloud Zone"
  type        = string
  default     = "europe-west4-a"
}

variable "domain" {
  description = "API domain"
  type        = string
  default     = "api.openetruscan.com"
}
