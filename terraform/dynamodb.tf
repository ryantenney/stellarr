# DynamoDB table for media requests (also stores rate limit entries)
resource "aws_dynamodb_table" "requests" {
  name         = "${local.name_prefix}-requests"
  billing_mode = "PAY_PER_REQUEST" # On-demand pricing, scales to zero

  hash_key  = "media_type" # Partition key: "movie" or "tv" (or "RATELIMIT#<ip>")
  range_key = "tmdb_id"    # Sort key: TMDB ID (or 0 for rate limit entries)

  attribute {
    name = "media_type"
    type = "S"
  }

  attribute {
    name = "tmdb_id"
    type = "N"
  }

  # TTL for automatic cleanup of rate limit entries
  ttl {
    attribute_name = "ttl"
    enabled        = true
  }

  tags = {
    Name = "${local.name_prefix}-requests"
  }
}
