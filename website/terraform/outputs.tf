output "s3_bucket_name" {
  description = "Name of the S3 bucket for website files"
  value       = aws_s3_bucket.website.id
}

output "cloudfront_distribution_id" {
  description = "CloudFront distribution ID"
  value       = aws_cloudfront_distribution.website.id
}

output "github_actions_role_arn" {
  description = "IAM role ARN for GitHub Actions OIDC"
  value       = aws_iam_role.github_actions_website.arn
}

output "website_url" {
  description = "Website URL"
  value       = "https://${var.domain_name}"
}
