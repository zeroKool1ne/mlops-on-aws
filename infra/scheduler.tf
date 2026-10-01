# EventBridge Scheduler, not cron on an EC2 instance (ADR-4). A t4g.nano to run
# two cron lines costs about $3 a month and has to be patched, monitored and
# restarted; the scheduler costs nothing at this volume and cannot fall over.
#
# EventBridge Scheduler rather than the older EventBridge Rules: it has native
# retry and dead-letter configuration per schedule, which a rule does not.

resource "aws_iam_role" "scheduler" {
  name = "${var.project}-scheduler-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Action    = "sts:AssumeRole"
      Principal = { Service = "scheduler.amazonaws.com" }
      # Without this the role could be assumed by any account that guesses the
      # ARN - the confused deputy problem, in its textbook form.
      Condition = {
        StringEquals = { "aws:SourceAccount" = data.aws_caller_identity.current.account_id }
      }
    }]
  })
}

resource "aws_iam_role_policy" "scheduler" {
  name = "${var.project}-scheduler-policy"
  role = aws_iam_role.scheduler.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = "lambda:InvokeFunction"
      Resource = [
        aws_lambda_function.ingest.arn,
        aws_lambda_function.monitor.arn,
      ]
    }]
  })
}

# A failed invocation that nobody sees is worse than no schedule at all: the
# feature table silently stops updating and the model keeps serving yesterday's
# world. Events that cannot be delivered land here instead of evaporating.
resource "aws_sqs_queue" "schedule_dlq" {
  name                      = "${var.project}-schedule-dlq"
  message_retention_seconds = 1209600 # 14 days, the maximum
  sqs_managed_sse_enabled   = true
}

resource "aws_iam_role_policy" "scheduler_dlq" {
  name = "${var.project}-scheduler-dlq-policy"
  role = aws_iam_role.scheduler.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = "sqs:SendMessage"
      Resource = aws_sqs_queue.schedule_dlq.arn
    }]
  })
}

# Ingestion: on weekdays only, after the US close. Gold futures settle at
# 17:00 New York; 23:30 UTC is comfortably after that and before midnight, so
# the partition date always matches the trading day. Weekends are skipped
# because there is no new data to fetch and a run would only cost money.
resource "aws_scheduler_schedule" "ingest" {
  name                = "${var.project}-daily-ingest"
  schedule_expression = var.ingest_schedule

  # Stated explicitly. The default is UTC, but a schedule whose timezone is
  # implicit is the kind of thing that breaks silently at a DST boundary.
  schedule_expression_timezone = "UTC"
  flexible_time_window { mode = "OFF" }

  target {
    arn      = aws_lambda_function.ingest.arn
    role_arn = aws_iam_role.scheduler.arn

    retry_policy {
      maximum_retry_attempts       = 3
      maximum_event_age_in_seconds = 3600
    }

    dead_letter_config {
      arn = aws_sqs_queue.schedule_dlq.arn
    }
  }
}

# Drift check: an hour after ingestion, so it scores data that has already
# landed. Running them together would be a race the monitor loses.
resource "aws_scheduler_schedule" "monitor" {
  name                         = "${var.project}-daily-drift-check"
  schedule_expression          = var.monitor_schedule
  schedule_expression_timezone = "UTC"
  flexible_time_window { mode = "OFF" }

  target {
    arn      = aws_lambda_function.monitor.arn
    role_arn = aws_iam_role.scheduler.arn

    retry_policy {
      maximum_retry_attempts       = 2
      maximum_event_age_in_seconds = 3600
    }

    dead_letter_config {
      arn = aws_sqs_queue.schedule_dlq.arn
    }
  }
}
