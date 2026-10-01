# Printed after `terraform apply`. These are the values the application code,
# the deployment pipeline and the presentation need, so they are read from here
# rather than copied out of the console by hand.

output "api_url" {
  description = "The live endpoint. Open it in a browser for the demo page, or POST to /predict."
  value       = aws_apigatewayv2_stage.default.invoke_url
}

output "demo_url" {
  description = "Same thing, spelled out for the presentation."
  value       = aws_apigatewayv2_stage.default.invoke_url
}

output "docs_url" {
  description = "Generated OpenAPI documentation."
  value       = "${aws_apigatewayv2_stage.default.invoke_url}docs"
}

output "data_bucket" {
  description = "S3 bucket holding raw data, features, model artifacts and drift reports."
  value       = aws_s3_bucket.data.id
}

output "ecr_repository_url" {
  description = "Push the container image here."
  value       = aws_ecr_repository.api.repository_url
}

output "dashboard_url" {
  description = "The operations dashboard: drift on the left, service health on the right."
  value       = "https://${var.region}.console.aws.amazon.com/cloudwatch/home?region=${var.region}#dashboards:name=${aws_cloudwatch_dashboard.main.dashboard_name}"
}

output "sns_topic_arn" {
  description = "Where drift, error and cost alerts are published."
  value       = aws_sns_topic.alerts.arn
}

output "sagemaker_role_arn" {
  description = "Role a training job or endpoint assumes. Passed to the SageMaker SDK."
  value       = aws_iam_role.sagemaker.arn
}

output "lambda_functions" {
  description = "All three functions, for the deployment pipeline to update."
  value = {
    api     = aws_lambda_function.api.function_name
    ingest  = aws_lambda_function.ingest.function_name
    monitor = aws_lambda_function.monitor.function_name
  }
}

output "region" {
  value = var.region
}

output "account_id" {
  description = "Resolved from the active credentials, never hard-coded."
  value       = data.aws_caller_identity.current.account_id
}
