# Application secrets in Secrets Manager

resource "random_password" "app_secret" {
  length  = 64
  special = false
}

resource "aws_secretsmanager_secret" "app_config" {
  name = "${local.name_prefix}-app-config-${local.name_suffix}"

  tags = {
    Name = "${local.name_prefix}-app-config"
  }
}

resource "aws_secretsmanager_secret_version" "app_config" {
  secret_id = aws_secretsmanager_secret.app_config.id
  secret_string = jsonencode({
    APP_SECRET_KEY     = random_password.app_secret.result
    PRESHARED_PASSWORD = var.preshared_password
    TMDB_API_KEY       = var.tmdb_api_key
    FEED_TOKEN         = var.feed_token
  })
}
