provider "aws" {
  region = var.aws_region
}

resource "aws_lambda_function" "skogapp_teig_lambda" {
  function_name = "skogappTeigLambda"
  handler       = "run.lambda_handler"
  runtime       = "python3.11"

  filename         = "deployment_package.zip"
  source_code_hash = filebase64sha256("deployment_package.zip")
  timeout          = 900  # 15 minutes

  role = aws_iam_role.lambda_exec_role.arn

  environment {
    variables = {
      POSTGIS_DBNAME = var.postgis_dbname
      POSTGIS_USERNAME = var.postgis_username
      POSTGIS_PASSWORD = var.postgis_password
      POSTGIS_HOST = var.postgis_host
    }
  }
}

resource "aws_iam_role" "lambda_exec_role" {
  name = "lambda_exec_role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Action = "sts:AssumeRole",
        Effect = "Allow",
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

resource "aws_api_gateway_rest_api" "skogapp_api" {
  name        = "skogapp_api"
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
  rest_api_id = aws_api_gateway_rest_api.skogapp_api.id
  resource_id = aws_api_gateway_resource.skogapp_resource.id
  http_method = aws_api_gateway_method.skogapp_method.http_method
  type        = "AWS_PROXY"
  integration_http_method = "POST"
  uri         = "arn:aws:apigateway:${var.aws_region}:lambda:path/2015-03-31/functions/${aws_lambda_function.skogapp_teig_lambda.arn}/invocations"
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