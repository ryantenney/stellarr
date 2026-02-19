variable "domain_name" {
  description = "Domain name for the marketing website"
  type        = string
  default     = "stellarr.dev"
}

variable "hosted_zone_id" {
  description = "Route53 hosted zone ID for the domain"
  type        = string
}

variable "github_repo" {
  description = "GitHub repository (owner/repo) for OIDC trust"
  type        = string
  default     = "ryantenney/stellarr"
}
