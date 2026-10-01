# Where the system tells a human that something needs attention. Three things
# publish here: the drift alarm, the API error alarm and the cost alarm.

resource "aws_sns_topic" "alerts" {
  name = "${var.project}-alerts"
}

# Enforce TLS on publish, for the same reason the bucket policy does.
resource "aws_sns_topic_policy" "alerts" {
  arn = aws_sns_topic.alerts.arn

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "AllowAccountPublish"
        Effect    = "Allow"
        Principal = { AWS = data.aws_caller_identity.current.account_id }
        Action    = "SNS:Publish"
        Resource  = aws_sns_topic.alerts.arn
      },
      {
        Sid       = "AllowCloudWatchAlarms"
        Effect    = "Allow"
        Principal = { Service = ["cloudwatch.amazonaws.com", "budgets.amazonaws.com"] }
        Action    = "SNS:Publish"
        Resource  = aws_sns_topic.alerts.arn
        Condition = {
          StringEquals = { "aws:SourceAccount" = data.aws_caller_identity.current.account_id }
        }
      },
      {
        Sid       = "DenyUnencryptedTransport"
        Effect    = "Deny"
        Principal = "*"
        Action    = "SNS:Publish"
        Resource  = aws_sns_topic.alerts.arn
        Condition = { Bool = { "aws:SecureTransport" = "false" } }
      },
    ]
  })
}

# Subscription is opt-in via variable: an email subscription has to be
# confirmed by clicking a link, so Terraform cannot complete it unattended.
# Leaving the address empty keeps `apply` clean for anyone who clones this.
resource "aws_sns_topic_subscription" "email" {
  count     = var.alert_email == "" ? 0 : 1
  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.alert_email
}
