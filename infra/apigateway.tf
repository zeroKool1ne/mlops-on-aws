# An HTTP API, not a REST API. The REST flavour costs $3.50 per million
# requests and buys request validation, API keys, usage plans and WAF
# integration. The HTTP flavour costs $1.00 per million and buys none of that.
# This service validates with Pydantic and has no paying consumers, so the
# extra features would be paid for and unused.

resource "aws_apigatewayv2_api" "api" {
  name          = "${var.project}-api"
  protocol_type = "HTTP"
  description   = "Gold/USD volatility forecasting API"

  # The demo page is served from the same origin as the API it calls, so CORS
  # is not needed for the demo itself. It is configured anyway, for GET and
  # POST only, so the endpoint can be called from a notebook or another page
  # during the presentation without a redeploy.
  cors_configuration {
    allow_origins = ["*"]
    allow_methods = ["GET", "POST", "OPTIONS"]
    allow_headers = ["content-type"]
    max_age       = 300
  }
}

resource "aws_apigatewayv2_integration" "api" {
  api_id = aws_apigatewayv2_api.api.id

  integration_type = "AWS_PROXY"
  integration_uri  = aws_lambda_function.api.invoke_arn

  # 2.0 hands the Lambda a compact event and lets it return a plain object.
  payload_format_version = "2.0"

  # Just under the Lambda timeout, so API Gateway is never the component that
  # gives up first. If it were shorter, a slow cold start would surface as a
  # gateway timeout with nothing in the Lambda log to explain it.
  timeout_milliseconds = min(var.api_timeout_seconds * 1000 - 1000, 30000)
}

# One catch-all route. FastAPI already owns routing, and duplicating its route
# table in API Gateway would mean every new endpoint needs a Terraform change.
resource "aws_apigatewayv2_route" "proxy" {
  api_id    = aws_apigatewayv2_api.api.id
  route_key = "ANY /{proxy+}"
  target    = "integrations/${aws_apigatewayv2_integration.api.id}"
}

# "/" is not matched by {proxy+}, so the demo page needs its own route.
resource "aws_apigatewayv2_route" "root" {
  api_id    = aws_apigatewayv2_api.api.id
  route_key = "ANY /"
  target    = "integrations/${aws_apigatewayv2_integration.api.id}"
}

resource "aws_cloudwatch_log_group" "apigw" {
  name              = "/aws/apigateway/${var.project}"
  retention_in_days = var.log_retention_days
}

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.api.id
  name        = "$default"
  auto_deploy = true

  # Access logging is off by default on HTTP APIs. Without it there is no
  # record of who called what, and a 500 can only be investigated from the
  # Lambda side.
  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.apigw.arn
    format = jsonencode({
      requestId      = "$context.requestId"
      ip             = "$context.identity.sourceIp"
      requestTime    = "$context.requestTime"
      httpMethod     = "$context.httpMethod"
      routeKey       = "$context.routeKey"
      status         = "$context.status"
      responseLength = "$context.responseLength"
      latency        = "$context.responseLatency"
      integrationErr = "$context.integrationErrorMessage"
    })
  }

  # A public endpoint with no authentication needs a ceiling, or a loop in
  # someone's script becomes a bill. Lambda concurrency would also cap it, but
  # only after the requests have already been paid for at the gateway.
  default_route_settings {
    throttling_rate_limit  = var.api_rate_limit
    throttling_burst_limit = var.api_burst_limit
  }
}

# API Gateway may invoke this function, and only from this API. Without the
# source_arn condition any API in the account could call it.
resource "aws_lambda_permission" "apigw" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.api.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.api.execution_arn}/*/*"
}
