variable "aws_region" {
  description = "AWS region to deploy to"
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Project name used for resource naming"
  type        = string
  default     = "overseer-lite"
}

variable "environment" {
  description = "Environment (dev, staging, prod)"
  type        = string
  default     = "prod"
}

variable "domain_name" {
  description = "Domain name for the application (e.g., overseer.example.com)"
  type        = string
}

variable "hosted_zone_id" {
  description = "Route53 hosted zone ID for the domain"
  type        = string
}

variable "tmdb_api_key" {
  description = "TMDB API key"
  type        = string
  sensitive   = true
}

variable "preshared_password" {
  description = "Password for user authentication"
  type        = string
  sensitive   = true
}

variable "feed_token" {
  description = "Token for protecting RSS/list endpoints"
  type        = string
  sensitive   = true
  default     = ""
}

variable "db_min_capacity" {
  description = "Minimum Aurora Serverless capacity units"
  type        = number
  default     = 0.5
}

variable "db_max_capacity" {
  description = "Maximum Aurora Serverless capacity units"
  type        = number
  default     = 2
}

variable "lambda_memory" {
  description = "Lambda function memory in MB"
  type        = number
  default     = 512
}

variable "lambda_timeout" {
  description = "Lambda function timeout in seconds"
  type        = number
  default     = 30
}

variable "enable_waf" {
  description = "Enable AWS WAF for rate limiting and threat protection"
  type        = bool
  default     = false
}

variable "waf_rate_limit" {
  description = "Maximum requests per 5-minute window per IP (WAF rate limiting)"
  type        = number
  default     = 100
}

variable "waf_auth_rate_limit" {
  description = "Maximum auth requests per 5-minute window per IP (minimum 100)"
  type        = number
  default     = 100  # AWS WAF minimum is 100

  validation {
    condition     = var.waf_auth_rate_limit >= 100
    error_message = "AWS WAF rate limit minimum is 100 requests per 5-minute window."
  }
}
