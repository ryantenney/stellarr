output "website_url" {
  description = "URL of the application"
  value       = "https://${var.domain_name}"
}

output "cloudfront_distribution_id" {
  description = "CloudFront distribution ID (for cache invalidation)"
  value       = aws_cloudfront_distribution.main.id
}

output "frontend_bucket_name" {
  description = "S3 bucket name for frontend deployment"
  value       = aws_s3_bucket.frontend.id
}

output "lambda_function_name" {
  description = "Lambda function name for backend deployment"
  value       = aws_lambda_function.api.function_name
}

output "lambda_deployment_bucket" {
  description = "S3 bucket for Lambda deployment packages"
  value       = aws_s3_bucket.lambda_deployment.id
}

output "lambda_function_url" {
  description = "Lambda function URL"
  value       = aws_lambda_function_url.api.function_url
}

output "dynamodb_table_name" {
  description = "DynamoDB table name for requests"
  value       = aws_dynamodb_table.requests.name
}

output "app_secret_arn" {
  description = "ARN of the application config secret"
  value       = aws_secretsmanager_secret.app_config.arn
}
