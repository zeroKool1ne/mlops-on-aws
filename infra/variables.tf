variable "project" {
  description = "Project name. Used as the prefix on every resource, because the account is shared."
  type        = string
  default     = "goldmlops"
}

variable "owner" {
  description = "Tag value identifying who owns these resources."
  type        = string
  default     = "daniel"
}

variable "region" {
  description = "AWS region. SageMaker serverless inference is available here."
  type        = string
  default     = "us-east-1"
}

variable "profile" {
  description = "Local AWS CLI profile. Switching this moves the whole stack to another account."
  type        = string
  default     = "default"
}

variable "raw_retention_days" {
  description = "Days before raw data moves to cheaper storage."
  type        = number
  default     = 30
}

variable "log_retention_days" {
  description = "Days before CloudWatch logs expire. Without this they are kept forever and billed forever."
  type        = number
  default     = 14
}

# --------------------------------------------------------------------------
# Container image
# --------------------------------------------------------------------------

variable "image_tag" {
  description = <<-TEXT
    Tag of the image in ECR that all three Lambdas run. Deliberately a variable
    rather than hard-coded "latest": a deployment is then a tag change, and a
    rollback is the previous tag. With "latest" there is nothing to roll back to.
  TEXT
  type        = string
  default     = "latest"
}

# --------------------------------------------------------------------------
# API sizing
# --------------------------------------------------------------------------

variable "api_memory_mb" {
  description = "Lambda memory for the API. On Lambda, memory is also CPU share."
  type        = number
  default     = 2048
}

variable "api_timeout_seconds" {
  description = "Must cover a cold start: image pull, model download, data fetch."
  type        = number
  default     = 60
}

variable "api_rate_limit" {
  description = "Steady-state requests per second at the gateway. A public endpoint with no auth needs a ceiling."
  type        = number
  default     = 10
}

variable "api_burst_limit" {
  description = "Burst allowance above the steady rate."
  type        = number
  default     = 20
}

variable "sagemaker_endpoint_name" {
  description = <<-TEXT
    Name of the SageMaker endpoint the API should forward to. Empty means the
    API loads the model into itself instead (see src/api/serving.py), which is
    how the service runs before the endpoint exists.
  TEXT
  type        = string
  default     = ""
}

# --------------------------------------------------------------------------
# Schedules
# --------------------------------------------------------------------------

variable "ingest_schedule" {
  description = <<-TEXT
    When to ingest. Weekdays after the US close: gold futures settle at 17:00
    New York, so 23:30 UTC is safely after it and still the same calendar day.
  TEXT
  type        = string
  default     = "cron(30 23 ? * MON-FRI *)"
}

variable "monitor_schedule" {
  description = "When to check drift. An hour after ingestion, so it scores data that has landed."
  type        = string
  default     = "cron(30 0 ? * TUE-SAT *)"
}

# --------------------------------------------------------------------------
# Alerting and cost
# --------------------------------------------------------------------------

variable "alert_email" {
  description = <<-TEXT
    Address subscribed to the alert topic. Left empty by default because an
    email subscription has to be confirmed by clicking a link, which Terraform
    cannot do - so a hard-coded address would leave a pending subscription
    behind for anyone who clones this.
  TEXT
  type        = string
  default     = ""
}

variable "monthly_budget_usd" {
  description = "Monthly spend on this project's tagged resources before an alert fires."
  type        = number
  default     = 20
}
