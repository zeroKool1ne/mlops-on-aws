# Account, region and profile are variables, never hard-coded. Changing the
# profile is the whole migration to a different AWS account (ADR-8).
provider "aws" {
  region  = var.region
  profile = var.profile

  # Every resource this stack creates carries these tags. That is what makes
  # cost tracking possible in a shared account, where an account-level budget
  # says nothing about this project.
  default_tags {
    tags = {
      Project   = var.project
      Owner     = var.owner
      ManagedBy = "terraform"
    }
  }
}
