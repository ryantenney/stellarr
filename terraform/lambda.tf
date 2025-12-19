# Lambda function for the FastAPI backend

# S3 bucket for Lambda deployment packages
resource "aws_s3_bucket" "lambda_deployment" {
  bucket = "${local.name_prefix}-lambda-deploy-${local.name_suffix}"

  tags = {
    Name = "${local.name_prefix}-lambda-deploy"
  }
}

resource "aws_s3_bucket_versioning" "lambda_deployment" {
  bucket = aws_s3_bucket.lambda_deployment.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_public_access_block" "lambda_deployment" {
  bucket = aws_s3_bucket.lambda_deployment.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# IAM role for Lambda
resource "aws_iam_role" "lambda" {
  name = "${local.name_prefix}-lambda-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })
}

# Lambda basic execution policy
resource "aws_iam_role_policy_attachment" "lambda_basic" {
  role       = aws_iam_role.lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# Secrets Manager access policy
resource "aws_iam_role_policy" "lambda_secrets" {
  name = "${local.name_prefix}-lambda-secrets"
  role = aws_iam_role.lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue"
        ]
        Resource = [
          aws_secretsmanager_secret.app_config.arn
        ]
      }
    ]
  })
}

# DynamoDB access policy
resource "aws_iam_role_policy" "lambda_dynamodb" {
  name = "${local.name_prefix}-lambda-dynamodb"
  role = aws_iam_role.lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem",
          "dynamodb:PutItem",
          "dynamodb:DeleteItem",
          "dynamodb:Query",
          "dynamodb:Scan"
        ]
        Resource = [
          aws_dynamodb_table.requests.arn
        ]
      }
    ]
  })
}

# Lambda function
resource "aws_lambda_function" "api" {
  function_name = "${local.name_prefix}-api"
  role          = aws_iam_role.lambda.arn
  handler       = "main.handler"
  runtime       = "python3.12"
  architectures = ["arm64"]  # Graviton2 - faster and 20% cheaper
  timeout       = var.lambda_timeout
  memory_size   = var.lambda_memory

  # Placeholder - will be updated by CI/CD
  filename         = data.archive_file.lambda_placeholder.output_path
  source_code_hash = data.archive_file.lambda_placeholder.output_base64sha256

  # No VPC - Lambda can access internet directly for TMDB API

  environment {
    variables = {
      DYNAMODB_TABLE            = aws_dynamodb_table.requests.name
      APP_SECRET_ARN            = aws_secretsmanager_secret.app_config.arn
      AWS_REGION_NAME           = var.aws_region
      BASE_URL                  = "https://${var.domain_name}"
      ALLOWED_ORIGIN            = "https://${var.domain_name}"
      RATE_LIMIT_ENABLED        = var.enable_rate_limiting ? "true" : "false"
      RATE_LIMIT_MAX_ATTEMPTS   = tostring(var.rate_limit_max_attempts)
      RATE_LIMIT_WINDOW_SECONDS = tostring(var.rate_limit_window_seconds)
    }
  }

  tags = {
    Name = "${local.name_prefix}-api"
  }
}

# Placeholder for initial deployment
data "archive_file" "lambda_placeholder" {
  type        = "zip"
  output_path = "${path.module}/.terraform/lambda_placeholder.zip"

  source {
    content  = "# Placeholder - deploy actual code via CI/CD"
    filename = "placeholder.py"
  }
}

# Lambda function URL (alternative to API Gateway, simpler)
resource "aws_lambda_function_url" "api" {
  function_name      = aws_lambda_function.api.function_name
  authorization_type = "NONE"

  cors {
    allow_origins     = ["https://${var.domain_name}"]
    allow_methods     = ["*"]
    allow_headers     = ["*"]
    allow_credentials = true
    max_age           = 3600
  }
}

# CloudWatch Log Group
resource "aws_cloudwatch_log_group" "lambda" {
  name              = "/aws/lambda/${aws_lambda_function.api.function_name}"
  retention_in_days = 14
}
