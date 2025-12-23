# Application secrets in Secrets Manager

resource "random_password" "app_secret" {
  length  = 64
  special = false
}

# Generate VAPID key pair for Web Push notifications
# Uses external script to generate a valid EC P-256 key pair
# terraform_data stores the result so it's only generated once
data "external" "vapid_keys" {
  program = ["python3", "${path.module}/generate_vapid_keys.py"]
}

# Store the generated keys so they persist across applies
resource "terraform_data" "vapid_keys" {
  input = {
    private_key = data.external.vapid_keys.result.private_key
    public_key  = data.external.vapid_keys.result.public_key
  }

  lifecycle {
    ignore_changes = [input]
  }
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
    APP_SECRET_KEY       = random_password.app_secret.result
    PRESHARED_PASSWORD   = var.preshared_password
    TMDB_API_KEY         = var.tmdb_api_key
    FEED_TOKEN           = var.feed_token
    PLEX_WEBHOOK_TOKEN   = var.plex_webhook_token
    PLEX_SERVER_NAME     = var.plex_server_name
    TVDB_API_KEY         = var.tvdb_api_key
    VAPID_PRIVATE_KEY    = terraform_data.vapid_keys.output.private_key
  })
}
