# Three Lambdas, three roles, three different permission sets. One shared role
# would be simpler and wrong: the API would be able to write to the data lake,
# and the ingestion job would be able to invoke the model. Least privilege is
# not ceremony here - the ingestion job runs unattended on a schedule, and it
# is the component most likely to be the one with a bug in it.

locals {
  bucket_arn = aws_s3_bucket.data.arn

  # Managed by AWS, maintained by AWS: permission to write to the function's
  # own log group and nothing else. Hand-rolling this is pure downside.
  lambda_logs = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

data "aws_iam_policy_document" "lambda_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

# --------------------------------------------------------------------------
# API: reads the model artifact, invokes the endpoint. Writes nothing.
# --------------------------------------------------------------------------

resource "aws_iam_role" "api" {
  name               = "${var.project}-api-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

resource "aws_iam_role_policy_attachment" "api_logs" {
  role       = aws_iam_role.api.name
  policy_arn = local.lambda_logs
}

data "aws_iam_policy_document" "api" {
  # Read-only, and only under the two prefixes it actually needs. The API has
  # no business reading raw market data or drift reports.
  statement {
    sid       = "ReadModelArtifacts"
    actions   = ["s3:GetObject"]
    resources = ["${local.bucket_arn}/models/*", "${local.bucket_arn}/features/*"]
  }

  statement {
    sid       = "ListBucketScopedToPrefixes"
    actions   = ["s3:ListBucket"]
    resources = [local.bucket_arn]
    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = ["models/*", "features/*"]
    }
  }

  # Invoking a named endpoint, not every endpoint in the account.
  statement {
    sid       = "InvokeOwnEndpoint"
    actions   = ["sagemaker:InvokeEndpoint"]
    resources = ["arn:aws:sagemaker:${var.region}:${data.aws_caller_identity.current.account_id}:endpoint/${var.project}-*"]
  }
}

resource "aws_iam_role_policy" "api" {
  name   = "${var.project}-api-policy"
  role   = aws_iam_role.api.id
  policy = data.aws_iam_policy_document.api.json
}

# --------------------------------------------------------------------------
# Ingestion: writes the data lake. Cannot touch the model or the endpoint.
# --------------------------------------------------------------------------

resource "aws_iam_role" "ingest" {
  name               = "${var.project}-ingest-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

resource "aws_iam_role_policy_attachment" "ingest_logs" {
  role       = aws_iam_role.ingest.name
  policy_arn = local.lambda_logs
}

data "aws_iam_policy_document" "ingest" {
  statement {
    sid       = "WriteDataLake"
    actions   = ["s3:PutObject", "s3:GetObject"]
    resources = ["${local.bucket_arn}/raw/*", "${local.bucket_arn}/features/*"]
  }

  # No s3:DeleteObject anywhere. The raw layer is append-only by design
  # (ADR-3), and a bug in a scheduled job that could delete history is a
  # category of accident worth making impossible rather than unlikely.
  statement {
    sid       = "ListBucket"
    actions   = ["s3:ListBucket"]
    resources = [local.bucket_arn]
  }
}

resource "aws_iam_role_policy" "ingest" {
  name   = "${var.project}-ingest-policy"
  role   = aws_iam_role.ingest.id
  policy = data.aws_iam_policy_document.ingest.json
}

# --------------------------------------------------------------------------
# Monitoring: reads features and the reference, writes reports and metrics.
# --------------------------------------------------------------------------

resource "aws_iam_role" "monitor" {
  name               = "${var.project}-monitor-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

resource "aws_iam_role_policy_attachment" "monitor_logs" {
  role       = aws_iam_role.monitor.name
  policy_arn = local.lambda_logs
}

data "aws_iam_policy_document" "monitor" {
  statement {
    sid       = "ReadFeaturesAndReference"
    actions   = ["s3:GetObject"]
    resources = ["${local.bucket_arn}/features/*", "${local.bucket_arn}/monitoring/*"]
  }

  statement {
    sid       = "WriteDriftReports"
    actions   = ["s3:PutObject"]
    resources = ["${local.bucket_arn}/monitoring/reports/*"]
  }

  statement {
    sid       = "ListBucket"
    actions   = ["s3:ListBucket"]
    resources = [local.bucket_arn]
  }

  # PutMetricData takes no resource ARN - the API is account-wide and cannot be
  # narrowed by resource. The namespace condition is the only available scope,
  # so it is used: this role can write GoldMLOps metrics and nothing else.
  statement {
    sid       = "PublishDriftMetric"
    actions   = ["cloudwatch:PutMetricData"]
    resources = ["*"]
    condition {
      test     = "StringEquals"
      variable = "cloudwatch:namespace"
      values   = ["GoldMLOps"]
    }
  }

  statement {
    sid       = "NotifyOnDrift"
    actions   = ["sns:Publish"]
    resources = [aws_sns_topic.alerts.arn]
  }
}

resource "aws_iam_role_policy" "monitor" {
  name   = "${var.project}-monitor-policy"
  role   = aws_iam_role.monitor.id
  policy = data.aws_iam_policy_document.monitor.json
}

# --------------------------------------------------------------------------
# SageMaker: assumed by training jobs and by the endpoint, not by a Lambda.
# --------------------------------------------------------------------------

resource "aws_iam_role" "sagemaker" {
  name = "${var.project}-sagemaker-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Action    = "sts:AssumeRole"
      Principal = { Service = "sagemaker.amazonaws.com" }
    }]
  })
}

data "aws_iam_policy_document" "sagemaker" {
  # A training job reads the feature table and writes the artifact back.
  statement {
    sid       = "ReadTrainingData"
    actions   = ["s3:GetObject", "s3:ListBucket"]
    resources = [local.bucket_arn, "${local.bucket_arn}/features/*", "${local.bucket_arn}/models/*"]
  }

  statement {
    sid       = "WriteArtifacts"
    actions   = ["s3:PutObject"]
    resources = ["${local.bucket_arn}/models/*", "${local.bucket_arn}/mlruns/*"]
  }

  # Pull the serving image. Scoped to this project's repository.
  statement {
    sid       = "PullImage"
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"]
  }

  statement {
    sid = "PullProjectImage"
    actions = [
      "ecr:BatchCheckLayerAvailability",
      "ecr:GetDownloadUrlForLayer",
      "ecr:BatchGetImage",
    ]
    resources = [aws_ecr_repository.api.arn]
  }

  statement {
    sid       = "WriteLogsAndMetrics"
    actions   = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["arn:aws:logs:${var.region}:${data.aws_caller_identity.current.account_id}:log-group:/aws/sagemaker/*"]
  }

  statement {
    sid       = "PublishTrainingMetrics"
    actions   = ["cloudwatch:PutMetricData"]
    resources = ["*"]
    condition {
      test     = "StringEquals"
      variable = "cloudwatch:namespace"
      values   = ["GoldMLOps", "/aws/sagemaker/TrainingJobs"]
    }
  }
}

resource "aws_iam_role_policy" "sagemaker" {
  name   = "${var.project}-sagemaker-policy"
  role   = aws_iam_role.sagemaker.id
  policy = data.aws_iam_policy_document.sagemaker.json
}
