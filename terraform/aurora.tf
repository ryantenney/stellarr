# Aurora Serverless v2 PostgreSQL

resource "random_password" "db_password" {
  length  = 32
  special = false
}

# Find latest available Aurora PostgreSQL version
data "aws_rds_engine_version" "postgresql" {
  engine             = "aurora-postgresql"
  preferred_versions = ["16.4", "16.3", "16.2", "16.1", "15.7", "15.6"]
}

resource "aws_rds_cluster" "main" {
  cluster_identifier = "${local.name_prefix}-aurora"
  engine             = "aurora-postgresql"
  engine_mode        = "provisioned"
  engine_version     = data.aws_rds_engine_version.postgresql.version
  database_name      = "overseer"
  master_username    = "overseer"
  master_password    = random_password.db_password.result

  db_subnet_group_name   = aws_db_subnet_group.aurora.name
  vpc_security_group_ids = [aws_security_group.aurora.id]

  serverlessv2_scaling_configuration {
    min_capacity = var.db_min_capacity
    max_capacity = var.db_max_capacity
  }

  skip_final_snapshot = var.environment != "prod"
  storage_encrypted   = true

  tags = {
    Name = "${local.name_prefix}-aurora"
  }
}

resource "aws_rds_cluster_instance" "main" {
  identifier         = "${local.name_prefix}-aurora-instance"
  cluster_identifier = aws_rds_cluster.main.id
  instance_class     = "db.serverless"
  engine             = aws_rds_cluster.main.engine
  engine_version     = aws_rds_cluster.main.engine_version

  tags = {
    Name = "${local.name_prefix}-aurora-instance"
  }
}

# Store DB credentials in Secrets Manager
resource "aws_secretsmanager_secret" "db_credentials" {
  name = "${local.name_prefix}-db-credentials-${local.name_suffix}"

  tags = {
    Name = "${local.name_prefix}-db-credentials"
  }
}

resource "aws_secretsmanager_secret_version" "db_credentials" {
  secret_id = aws_secretsmanager_secret.db_credentials.id
  secret_string = jsonencode({
    host     = aws_rds_cluster.main.endpoint
    port     = aws_rds_cluster.main.port
    database = aws_rds_cluster.main.database_name
    username = aws_rds_cluster.main.master_username
    password = random_password.db_password.result
  })
}
