# Pinned so that `terraform apply` behaves the same next month as it does today.
# A floating provider version is the quiet cause of "it worked yesterday".
terraform {
  required_version = ">= 1.5"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}
