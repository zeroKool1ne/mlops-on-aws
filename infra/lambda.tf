# Three functions from one image (see the Dockerfile). The only difference
# between them is the handler in image_config.command, the role, and how much
# memory and time they get - which is exactly as much difference as there
# actually is between them.

locals {
  image = "${aws_ecr_repository.api.repository_url}:${var.image_tag}"
}

# Log groups are declared rather than left to Lambda. A group Lambda creates
# implicitly has no retention policy, which means logs are kept forever and
# billed forever - the single most common silent cost in a serverless account.
resource "aws_cloudwatch_log_group" "api" {
  name              = "/aws/lambda/${var.project}-api"
  retention_in_days = var.log_retention_days
}

resource "aws_cloudwatch_log_group" "ingest" {
  name              = "/aws/lambda/${var.project}-ingest"
  retention_in_days = var.log_retention_days
}

resource "aws_cloudwatch_log_group" "monitor" {
  name              = "/aws/lambda/${var.project}-monitor"
  retention_in_days = var.log_retention_days
}

# --------------------------------------------------------------------------
# API
# --------------------------------------------------------------------------

resource "aws_lambda_function" "api" {
  function_name = "${var.project}-api"
  role          = aws_iam_role.api.arn
  package_type  = "Image"
  image_uri     = local.image
  architectures = ["arm64"]

  # Memory is also CPU on Lambda: a function with more memory gets a
  # proportionally larger share of a core. 2048 MB is not about holding the
  # model - that needs about 100 MB - it is about unpickling it and running
  # pandas fast enough that the cold start stays tolerable.
  memory_size = var.api_memory_mb

  # Generous because a cold start has to download a 1.6 GB image, unpack the
  # model from S3 and fetch a year of market data. A warm invocation answers in
  # well under a second.
  timeout = var.api_timeout_seconds

  image_config {
    command = ["src.api.handler.handler"]
  }

  environment {
    variables = {
      MODEL_S3_URI = "s3://${aws_s3_bucket.data.id}/models/current/model.tar.gz"
      DATA_BUCKET  = aws_s3_bucket.data.id
      LOG_LEVEL    = "INFO"

      # Empty until the SageMaker endpoint exists. serving.py reads this and
      # falls back to loading the model into the function itself, so the API
      # works before the endpoint is deployed and switches over without a code
      # change afterwards.
      SAGEMAKER_ENDPOINT = var.sagemaker_endpoint_name
    }
  }

  depends_on = [aws_cloudwatch_log_group.api]
}

# --------------------------------------------------------------------------
# Daily ingestion
# --------------------------------------------------------------------------

resource "aws_lambda_function" "ingest" {
  function_name = "${var.project}-ingest"
  role          = aws_iam_role.ingest.arn
  package_type  = "Image"
  image_uri     = local.image
  architectures = ["arm64"]

  # Ten years of five instruments, plus the feature pipeline, held in memory at
  # once. Measured, not guessed: the job peaks around 700 MB.
  memory_size = 1536
  timeout     = 300

  image_config {
    command = ["src.data.ingest.handler"]
  }

  environment {
    variables = {
      DATA_BUCKET = aws_s3_bucket.data.id
      LOG_LEVEL   = "INFO"
    }
  }

  depends_on = [aws_cloudwatch_log_group.ingest]
}

# --------------------------------------------------------------------------
# Daily drift check
# --------------------------------------------------------------------------

resource "aws_lambda_function" "monitor" {
  function_name = "${var.project}-monitor"
  role          = aws_iam_role.monitor.arn
  package_type  = "Image"
  image_uri     = local.image
  architectures = ["arm64"]

  memory_size = 1024
  timeout     = 180

  image_config {
    command = ["src.monitoring.handler.handler"]
  }

  environment {
    variables = {
      DATA_BUCKET   = aws_s3_bucket.data.id
      SNS_TOPIC_ARN = aws_sns_topic.alerts.arn
      LOG_LEVEL     = "INFO"
    }
  }

  depends_on = [aws_cloudwatch_log_group.monitor]
}
