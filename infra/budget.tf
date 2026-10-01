# A budget is not cost optimisation, it is the seatbelt. The optimisation is
# everything else: serverless with no idle cost, arm64, lifecycle rules, log
# retention, an HTTP API instead of a REST API. This is what catches the case
# where one of those assumptions turns out to be wrong.
#
# The account is shared (ADR-8), so an account-level budget says nothing about
# this project. The filter is on the Project tag, which every resource in this
# stack carries through the provider's default_tags.

resource "aws_budgets_budget" "project" {
  name         = "${var.project}-monthly"
  budget_type  = "COST"
  limit_amount = tostring(var.monthly_budget_usd)
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  cost_filter {
    name   = "TagKeyValue"
    values = ["user:Project$${var.project}"]
  }

  # Forecast first: an alert at 80 percent of actual spend arrives when four
  # fifths of the money is already gone. A forecast alert arrives while there
  # is still time to do something about it.
  notification {
    comparison_operator       = "GREATER_THAN"
    threshold                 = 80
    threshold_type            = "PERCENTAGE"
    notification_type         = "FORECASTED"
    subscriber_sns_topic_arns = [aws_sns_topic.alerts.arn]
  }

  notification {
    comparison_operator       = "GREATER_THAN"
    threshold                 = 100
    threshold_type            = "PERCENTAGE"
    notification_type         = "ACTUAL"
    subscriber_sns_topic_arns = [aws_sns_topic.alerts.arn]
  }
}
