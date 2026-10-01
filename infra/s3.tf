# The data lake. One bucket, four prefixes, each with a different lifecycle
# (ADR-3). Separate buckets per prefix would multiply the IAM policies without
# isolating anything that actually needs isolating.
#
#   raw/          one immutable Parquet partition per ingestion run
#   features/     the current model-ready table, rewritten daily
#   models/       model.tar.gz artifacts, versioned
#   monitoring/   drift references and reports
#   mlruns/       MLflow artifact store (ADR-9)

resource "aws_s3_bucket" "data" {
  # The account ID is part of the name because S3 bucket names are globally
  # unique across all of AWS, not per account. "goldmlops-data" would collide
  # with the next person who tries it.
  bucket = "${var.project}-data-${data.aws_caller_identity.current.account_id}"
}

# Versioning is the undo button for a bad ingestion run or an overwritten
# model artifact. Without it, a bug that writes garbage to features/latest
# destroys the only copy.
resource "aws_s3_bucket_versioning" "data" {
  bucket = aws_s3_bucket.data.id
  versioning_configuration {
    status = "Enabled"
  }
}

# SSE-S3 rather than SSE-KMS: encryption at rest is required, but a customer
# managed key costs $1/month plus per-request charges and buys nothing here,
# because nobody outside this account needs to be denied access to the key
# separately from the data.
resource "aws_s3_bucket_server_side_encryption_configuration" "data" {
  bucket = aws_s3_bucket.data.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
    bucket_key_enabled = true
  }
}

# Nothing in this bucket is ever public. The API is the only intended way in,
# and it goes through API Gateway. This block makes an accidental public ACL
# impossible rather than merely unlikely.
resource "aws_s3_bucket_public_access_block" "data" {
  bucket                  = aws_s3_bucket.data.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Deny any request that is not TLS. Without this, encryption in transit is a
# convention rather than a rule.
resource "aws_s3_bucket_policy" "tls_only" {
  bucket = aws_s3_bucket.data.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "DenyUnencryptedTransport"
      Effect    = "Deny"
      Principal = "*"
      Action    = "s3:*"
      Resource = [
        aws_s3_bucket.data.arn,
        "${aws_s3_bucket.data.arn}/*",
      ]
      Condition = {
        Bool = { "aws:SecureTransport" = "false" }
      }
    }]
  })

  depends_on = [aws_s3_bucket_public_access_block.data]
}

resource "aws_s3_bucket_lifecycle_configuration" "data" {
  bucket = aws_s3_bucket.data.id

  # Raw partitions are written once and read only when a training run has to be
  # reproduced, which is rare. Standard-IA is about 45 % cheaper per GB and the
  # slower first-byte latency is irrelevant for a batch read.
  rule {
    id     = "raw-to-infrequent-access"
    status = "Enabled"
    filter { prefix = "raw/" }

    transition {
      days          = var.raw_retention_days
      storage_class = "STANDARD_IA"
    }
  }

  # Versioning keeps every overwritten features/latest file forever unless told
  # otherwise. Ninety days is enough to recover from a mistake and short enough
  # that the bill does not grow without limit.
  rule {
    id     = "expire-old-versions"
    status = "Enabled"
    filter {}

    noncurrent_version_expiration {
      noncurrent_days = 90
    }
  }

  # A failed multipart upload leaves its parts behind and bills for them
  # silently, with nothing visible in the console to explain the charge.
  rule {
    id     = "abort-incomplete-uploads"
    status = "Enabled"
    filter {}

    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }
}
