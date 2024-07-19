provider "aws" {
  region = var.aws_region
}

data "aws_caller_identity" "current" {}

resource "aws_secretsmanager_secret" "postgis_secret" {
  name = var.secret_name
}

resource "aws_secretsmanager_secret_version" "postgis_secret_version" {
  secret_id = aws_secretsmanager_secret.postgis_secret.id

  secret_string = jsonencode({
    POSTGIS_DBNAME   = var.postgis_dbname,
    POSTGIS_USERNAME = var.postgis_username,
    POSTGIS_PASSWORD = var.postgis_password,
    POSTGIS_HOST     = var.postgis_host
  })
}

data "aws_security_group" "existing_lambda_sg" {
  filter {
    name   = "group-name"
    values = ["lambda_sg"]
  }

  filter {
    name   = "vpc-id"
    values = [var.aws_vpc_id]
  }
}

resource "aws_security_group" "lambda_sg" {
  count       = length(data.aws_security_group.existing_lambda_sg.id) == 0 ? 1 : 0
  name        = "lambda_sg"
  description = "Security group for Lambda function"
  vpc_id      = var.aws_vpc_id
}

resource "aws_security_group_rule" "lambda_ingress_postgres" {
  type                     = "ingress"
  from_port                = 5432
  to_port                  = 5432
  protocol                 = "tcp"
  security_group_id        = var.rds_sg_id
  source_security_group_id = length(data.aws_security_group.existing_lambda_sg.id) == 0 ? aws_security_group.lambda_sg[0].id : data.aws_security_group.existing_lambda_sg.id
}

resource "aws_security_group_rule" "allow_lambda_egress" {
  type              = "egress"
  from_port         = 0
  to_port           = 0
  protocol          = "-1"  # All traffic
  security_group_id = length(data.aws_security_group.existing_lambda_sg.id) == 0 ? aws_security_group.lambda_sg[0].id : data.aws_security_group.existing_lambda_sg.id
  cidr_blocks       = ["0.0.0.0/0"]
}

resource "aws_lambda_function" "skogapp_teig_lambda" {
  function_name = "skogappTeigLambda"
  handler       = "run.lambda_handler"
  runtime       = "python3.12"

  filename         = "deployment_package.zip"
  source_code_hash = filebase64sha256("deployment_package.zip")
  timeout          = 900  # 15 minutes

  role = aws_iam_role.lambda_exec_role.arn

  environment {
    variables = {
      SECRET_NAME = var.secret_name
    }
  }

  vpc_config {
    subnet_ids         = split(",", var.aws_subnet_ids)
    security_group_ids = [length(data.aws_security_group.existing_lambda_sg.id) == 0 ? aws_security_group.lambda_sg[0].id : data.aws_security_group.existing_lambda_sg.id]
  }
}

resource "aws_iam_role" "lambda_exec_role" {
  name = "lambda_exec_role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Action    = "sts:AssumeRole",
        Effect    = "Allow",
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "lambda_exec_policy" {
  role       = aws_iam_role.lambda_exec_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "lambda_secret_access_policy" {
  name = "lambda_secret_access_policy"
  role = aws_iam_role.lambda_exec_role.id

  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Action = [
          "secretsmanager:GetSecretValue"
        ],
        Effect   = "Allow",
        Resource = "arn:aws:secretsmanager:${var.aws_region}:${data.aws_caller_identity.current.account_id}:secret:${var.secret_name}*"
      }
    ]
  })
}

resource "aws_api_gateway_rest_api" "skogapp_api" {
  name        = "skogapp-api"
  description = "API for SkogApp"
}

resource "aws_api_gateway_resource" "skogapp_resource" {
  rest_api_id = aws_api_gateway_rest_api.skogapp_api.id
  parent_id   = aws_api_gateway_rest_api.skogapp_api.root_resource_id
  path_part   = "filter"
}

resource "aws_api_gateway_method" "skogapp_method" {
  rest_api_id   = aws_api_gateway_rest_api.skogapp_api.id
  resource_id   = aws_api_gateway_resource.skogapp_resource.id
  http_method   = "POST"
  authorization = "NONE"
}

resource "aws_api_gateway_integration" "skogapp_integration" {
  rest_api_id             = aws_api_gateway_rest_api.skogapp_api.id
  resource_id             = aws_api_gateway_resource.skogapp_resource.id
  http_method             = aws_api_gateway_method.skogapp_method.http_method
  type                    = "AWS_PROXY"
  integration_http_method = "POST"
  uri                     = "arn:aws:apigateway:${var.aws_region}:lambda:path/2015-03-31/functions/${aws_lambda_function.skogapp_teig_lambda.arn}/invocations"
}

resource "aws_lambda_permission" "skogapp_api_gateway" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.skogapp_teig_lambda.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_api_gateway_rest_api.skogapp_api.execution_arn}/*/*"
}

output "api_endpoint" {
  value = "${aws_api_gateway_rest_api.skogapp_api.execution_arn}/filter"
}