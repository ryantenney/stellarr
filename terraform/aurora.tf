# Temporary file to allow clean destruction of Aurora cluster
# DELETE THIS FILE after terraform apply completes successfully

resource "random_password" "db_password" {
  length  = 32
  special = false
}

resource "aws_secretsmanager_secret" "db_credentials" {
  name = "${local.name_prefix}-db-creds-${local.name_suffix}"

  tags = {
    Name = "${local.name_prefix}-db-creds"
  }
}

resource "aws_secretsmanager_secret_version" "db_credentials" {
  secret_id = aws_secretsmanager_secret.db_credentials.id
  secret_string = jsonencode({
    username = "overseer"
    password = random_password.db_password.result
    host     = aws_rds_cluster.main.endpoint
    port     = 5432
    database = "overseer"
  })
}

resource "aws_rds_cluster" "main" {
  cluster_identifier      = "${local.name_prefix}-aurora"
  engine                  = "aurora-postgresql"
  engine_mode             = "provisioned"
  engine_version          = "15.4"
  database_name           = "overseer"
  master_username         = "overseer"
  master_password         = random_password.db_password.result
  db_subnet_group_name    = aws_db_subnet_group.aurora.name
  vpc_security_group_ids  = [aws_security_group.aurora.id]
  skip_final_snapshot     = true  # IMPORTANT: Skip snapshot on deletion
  apply_immediately       = true

  serverlessv2_scaling_configuration {
    min_capacity = 0.5
    max_capacity = 2
  }

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
