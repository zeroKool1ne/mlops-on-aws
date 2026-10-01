# Monitoring, in the sense the rubric means it: numbers that can be alarmed on
# and a single page a human can look at. A log line is not monitoring - nobody
# reads logs until something has already gone wrong.

# --------------------------------------------------------------------------
# Alarms
# --------------------------------------------------------------------------

# The one that matters for the model: the incoming data has moved away from
# what the running model was trained on. 0.25 is the industry convention for
# "significant" PSI (see drift.py), not a statistically derived threshold.
resource "aws_cloudwatch_metric_alarm" "drift" {
  alarm_name        = "${var.project}-data-drift"
  alarm_description = <<-TEXT
    Maximum feature PSI crossed 0.25 — the incoming data has moved away from
    the distribution the running model was trained on. Review the drift report
    in s3://${aws_s3_bucket.data.id}/monitoring/reports/ before retraining:
    a genuine regime change calls for a new model, a broken feed calls for a fix.
  TEXT

  namespace   = "GoldMLOps"
  metric_name = "MaxFeaturePSI"
  statistic   = "Maximum"
  period      = 86400 # one day, matching how often the metric is produced

  comparison_operator = "GreaterThanThreshold"
  threshold           = 0.25
  evaluation_periods  = 1

  # The metric only exists on days the check ran. Treating a missing day as
  # breaching would alarm every weekend; treating it as OK would hide a monitor
  # that has stopped running, which is why the separate "monitor failed" alarm
  # below exists.
  treat_missing_data = "notBreaching"

  alarm_actions = [aws_sns_topic.alerts.arn]
  ok_actions    = [aws_sns_topic.alerts.arn]
}

# Monitoring that has quietly died looks exactly like monitoring that has
# nothing to report. This is the alarm that tells the difference.
resource "aws_cloudwatch_metric_alarm" "monitor_failed" {
  alarm_name        = "${var.project}-drift-check-failing"
  alarm_description = "The scheduled drift check errored. Drift is no longer being measured."

  namespace   = "AWS/Lambda"
  metric_name = "Errors"
  dimensions  = { FunctionName = aws_lambda_function.monitor.function_name }
  statistic   = "Sum"
  period      = 86400

  comparison_operator = "GreaterThanOrEqualToThreshold"
  threshold           = 1
  evaluation_periods  = 1
  treat_missing_data  = "notBreaching"

  alarm_actions = [aws_sns_topic.alerts.arn]
}

resource "aws_cloudwatch_metric_alarm" "ingest_failed" {
  alarm_name        = "${var.project}-ingestion-failing"
  alarm_description = "Daily ingestion errored. The feature table is going stale."

  namespace   = "AWS/Lambda"
  metric_name = "Errors"
  dimensions  = { FunctionName = aws_lambda_function.ingest.function_name }
  statistic   = "Sum"
  period      = 86400

  comparison_operator = "GreaterThanOrEqualToThreshold"
  threshold           = 1
  evaluation_periods  = 1
  treat_missing_data  = "notBreaching"

  alarm_actions = [aws_sns_topic.alerts.arn]
}

# API errors: a 5xx rate, not a count. One error in ten requests is a problem;
# one in ten thousand during a cold start is not.
resource "aws_cloudwatch_metric_alarm" "api_errors" {
  alarm_name        = "${var.project}-api-errors"
  alarm_description = "More than 10 percent of API invocations failed over 15 minutes."

  comparison_operator = "GreaterThanThreshold"
  threshold           = 10
  evaluation_periods  = 1
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alerts.arn]

  metric_query {
    id          = "error_rate"
    expression  = "100 * errors / MAX([invocations, 1])"
    label       = "Error rate (%)"
    return_data = true
  }

  metric_query {
    id = "errors"
    metric {
      namespace   = "AWS/Lambda"
      metric_name = "Errors"
      dimensions  = { FunctionName = aws_lambda_function.api.function_name }
      stat        = "Sum"
      period      = 900
    }
  }

  metric_query {
    id = "invocations"
    metric {
      namespace   = "AWS/Lambda"
      metric_name = "Invocations"
      dimensions  = { FunctionName = aws_lambda_function.api.function_name }
      stat        = "Sum"
      period      = 900
    }
  }
}

# --------------------------------------------------------------------------
# Dashboard
# --------------------------------------------------------------------------

resource "aws_cloudwatch_dashboard" "main" {
  dashboard_name = var.project

  dashboard_body = jsonencode({
    widgets = [
      {
        type = "text", x = 0, y = 0, width = 24, height = 2
        properties = {
          markdown = join("\n", [
            "# Gold/USD Forecasting — operations",
            "Model drift on the left, service health on the right. ",
            "Drift is measured once a day after ingestion; a gap in that line means the check did not run.",
          ])
        }
      },
      {
        type = "metric", x = 0, y = 2, width = 12, height = 6
        properties = {
          title  = "Feature drift (PSI) — alarm at 0.25"
          view   = "timeSeries"
          region = var.region
          period = 86400
          stat   = "Maximum"
          metrics = [
            ["GoldMLOps", "MaxFeaturePSI", { label = "worst feature" }],
            ["GoldMLOps", "MeanFeaturePSI", { label = "average" }],
          ]
          yAxis = { left = { min = 0 } }
          annotations = {
            horizontal = [
              { value = 0.10, label = "moderate", color = "#e7b416" },
              { value = 0.25, label = "significant", color = "#d13212" },
            ]
          }
        }
      },
      {
        type = "metric", x = 12, y = 2, width = 12, height = 6
        properties = {
          title  = "API — invocations and errors"
          view   = "timeSeries"
          region = var.region
          period = 300
          stat   = "Sum"
          metrics = [
            ["AWS/Lambda", "Invocations", "FunctionName", aws_lambda_function.api.function_name, { label = "invocations" }],
            ["AWS/Lambda", "Errors", "FunctionName", aws_lambda_function.api.function_name, { label = "errors", color = "#d13212" }],
            ["AWS/Lambda", "Throttles", "FunctionName", aws_lambda_function.api.function_name, { label = "throttles", color = "#e7b416" }],
          ]
        }
      },
      {
        type = "metric", x = 0, y = 8, width = 12, height = 6
        properties = {
          title  = "API latency — p50 against p99"
          view   = "timeSeries"
          region = var.region
          period = 300
          metrics = [
            ["AWS/Lambda", "Duration", "FunctionName", aws_lambda_function.api.function_name, { stat = "p50", label = "p50" }],
            ["AWS/Lambda", "Duration", "FunctionName", aws_lambda_function.api.function_name, { stat = "p99", label = "p99 (cold starts)" }],
          ]
          yAxis = { left = { label = "ms", showUnits = false } }
        }
      },
      {
        type = "metric", x = 12, y = 8, width = 12, height = 6
        properties = {
          title  = "Scheduled jobs — did they run and did they succeed"
          view   = "timeSeries"
          region = var.region
          period = 86400
          stat   = "Sum"
          metrics = [
            ["AWS/Lambda", "Invocations", "FunctionName", aws_lambda_function.ingest.function_name, { label = "ingestion runs" }],
            ["AWS/Lambda", "Errors", "FunctionName", aws_lambda_function.ingest.function_name, { label = "ingestion errors", color = "#d13212" }],
            ["AWS/Lambda", "Invocations", "FunctionName", aws_lambda_function.monitor.function_name, { label = "drift checks" }],
            ["AWS/Lambda", "Errors", "FunctionName", aws_lambda_function.monitor.function_name, { label = "drift errors", color = "#ff7f0e" }],
          ]
        }
      },
      {
        type = "log", x = 0, y = 14, width = 24, height = 6
        properties = {
          title  = "API errors, most recent first"
          region = var.region
          query = join(" | ", [
            "SOURCE '${aws_cloudwatch_log_group.api.name}'",
            "fields @timestamp, @message",
            "filter @message like /ERROR|Traceback|Task timed out/",
            "sort @timestamp desc",
            "limit 20",
          ])
          view = "table"
        }
      },
    ]
  })
}
