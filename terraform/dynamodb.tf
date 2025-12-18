# DynamoDB table for media requests
resource "aws_dynamodb_table" "requests" {
  name         = "${local.name_prefix}-requests"
  billing_mode = "PAY_PER_REQUEST" # On-demand pricing, scales to zero

  hash_key  = "media_type" # Partition key: "movie" or "tv"
  range_key = "tmdb_id"    # Sort key: TMDB ID

  attribute {
    name = "media_type"
    type = "S"
  }

  attribute {
    name = "tmdb_id"
    type = "N"
  }

  tags = {
    Name = "${local.name_prefix}-requests"
  }
}
