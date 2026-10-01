# Resolved from whatever credentials are active. Hard-coding an account ID
# would break the migration path in ADR-8 and leak it into a public repo.
data "aws_caller_identity" "current" {}

data "aws_region" "current" {}
