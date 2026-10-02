# AWS setup guide

Everything in this project is Terraform. There is no step below that asks you
to click something in the console, and that is deliberate: a deployment that
depends on remembering which checkbox to tick is not reproducible (ADR-5).

The whole stack is 46 resources in one state. It can be destroyed and rebuilt
in about fifteen minutes.

---

## Table of contents

- [What gets created](#what-gets-created)
- [Prerequisites](#prerequisites)
- [Deploying from scratch](#deploying-from-scratch)
- [Updating the application](#updating-the-application)
- [Verifying the deployment](#verifying-the-deployment)
- [What it costs](#what-it-costs)
- [Where the money would go if this grew](#where-the-money-would-go-if-this-grew)
- [Tearing it down](#tearing-it-down)
- [Moving to another account](#moving-to-another-account)
- [Troubleshooting](#troubleshooting)

---

## What gets created

![Architecture overview](diagrams/01_architecture_overview.png)

| Service | Resource | Why this one |
|---|---|---|
| **S3** | one bucket, four prefixes | Versioned, encrypted, public access blocked, non-TLS requests denied by bucket policy. Lifecycle moves `raw/` to Standard-IA and expires superseded versions after 30 days (ADR-3) |
| **ECR** | one repository | The image is 1.6 GB; a ZIP Lambda caps at 250 MB unpacked. Lifecycle keeps the 10 most recent images (ADR-13) |
| **Lambda** | three functions, one image | API, daily ingestion, daily drift check. Same image, different `CMD`, different role, different memory |
| **API Gateway** | HTTP API, `$default` stage | $1.00 per million requests against $3.50 for REST. Access logging and throttling on |
| **EventBridge Scheduler** | two schedules | Ingestion on weekdays after the US close, drift check an hour later. Retries and an SQS dead-letter queue (ADR-4) |
| **SQS** | one dead-letter queue | A scheduled invocation that fails silently is worse than no schedule at all |
| **SNS** | one topic | Drift, error and cost alerts |
| **CloudWatch** | 4 alarms, 1 dashboard, 4 log groups | Log groups are declared, not left to Lambda, so they have a retention policy |
| **IAM** | 5 roles, 6 policies | One role per function. The API cannot write to the data lake; ingestion has no `DeleteObject` anywhere |
| **Budgets** | one monthly budget | Filtered on the `Project` tag, because the account is shared (ADR-8) |

---

## Prerequisites

| Tool | Version | Why |
|---|---|---|
| Terraform | ≥ 1.5 | Provider version is pinned in `versions.tf` |
| AWS CLI | v2 | Credentials and the ECR login |
| Docker | with `buildx` | The image is `linux/arm64`; building on an Intel machine needs emulation |
| An AWS account | — | With permission for IAM, Lambda, S3, ECR, API Gateway, SageMaker, EventBridge, SNS, SQS, CloudWatch and Budgets |

```bash
aws sts get-caller-identity   # confirm you are in the right account
terraform -version
docker buildx version
```

> **On a shared account.** Every resource is prefixed with `var.project` and
> tagged `Project`, `Owner` and `ManagedBy`. Change `project` in
> `infra/variables.tf` if `goldmlops` is taken. The budget filter depends on
> that tag — an untagged resource is invisible to it.

---

## Deploying from scratch

The order matters once: Lambda needs an image, and the image needs a
repository to be pushed to. So the registry is created first, then the image
is built, then everything else.

### 1. The registry and the bucket

```bash
cd infra
terraform init
terraform apply -target=aws_ecr_repository.api -target=aws_s3_bucket.data
```

### 2. Build and push the image

```bash
cd ..
ECR=$(terraform -chdir=infra output -raw ecr_repository_url)
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin "${ECR%%/*}"
docker build --platform linux/arm64 -t "$ECR:latest" .
docker push "$ECR:latest"
```

### 3. A model to serve

The API needs an artifact in `models/current/`. Train one locally and upload it:

```bash
python -m src.models.train --target volatility --fetch-if-missing
python -m src.models.evaluate --model-dir artifacts --fetch-if-missing
tar -czf model.tar.gz -C artifacts model.joblib metadata.json
aws s3 cp model.tar.gz "s3://$(terraform -chdir=infra output -raw data_bucket)/models/current/model.tar.gz"
```

### 4. The rest of the stack

```bash
terraform -chdir=infra apply
```

`apply` prints the URLs you need:

```
api_url       = https://xxxxxxxxxx.execute-api.us-east-1.amazonaws.com/
dashboard_url = https://us-east-1.console.aws.amazon.com/cloudwatch/...
data_bucket   = goldmlops-data-<account-id>
```

### 5. Fill the data lake

The first ingestion has to be triggered by hand; after that the schedule
handles it.

```bash
aws lambda invoke --function-name goldmlops-ingest --payload '{}' /dev/stdout
```

### 6. Alerts by email (optional)

```bash
terraform -chdir=infra apply -var='alert_email=you@example.com'
```

AWS sends a confirmation link that has to be clicked. Terraform cannot do that
step, which is why the address is a variable with an empty default rather than
something hard-coded.

---

## Updating the application

Code change, new image, new tag. The tag is a variable so that a rollback is
the previous tag rather than a rebuild:

```bash
TAG=$(git rev-parse --short HEAD)
docker build --platform linux/arm64 -t "$ECR:$TAG" .
docker push "$ECR:$TAG"
terraform -chdir=infra apply -var="image_tag=$TAG"
```

Rolling back:

```bash
terraform -chdir=infra apply -var="image_tag=<previous-sha>"
```

---

## Verifying the deployment

```bash
API=$(terraform -chdir=infra output -raw api_url)

curl -s "$API/health" | jq
curl -s -X POST "$API/predict" -H 'content-type: application/json' -d '{}' | jq
```

A healthy response names the loaded model and where it is being served from:

```json
{ "status": "ok", "target": "volatility", "model_loaded": true,
  "serving_mode": "local", "n_features": 29 }
```

The first call after a quiet period is slow — the container image has to be
pulled and the model unpacked. Warm calls answer in well under a second.
Before a live demo, call `/health` once to warm it.

Then check the scheduled side:

```bash
aws lambda invoke --function-name goldmlops-monitor --payload '{}' /dev/stdout
aws s3 ls "s3://$(terraform -chdir=infra output -raw data_bucket)/monitoring/reports/" --recursive
```

---

## What it costs

Measured against the us-east-1 price list, at this project's actual volume:
22 ingestion runs and 22 drift checks a month, and a few hundred API calls.

| Service | What drives the cost | Monthly |
|---|---|---|
| CloudWatch — custom metrics | 3 metrics × $0.30 | **$0.90** |
| CloudWatch — alarms | 4 alarms × $0.10 | **$0.40** |
| ECR storage | 1.6 GB × $0.10/GB | **$0.16** |
| Lambda — ingestion | 22 runs × ~90 s × 1.5 GB, arm64 | **$0.04** |
| Lambda — API | a few hundred invocations | **$0.02** |
| Lambda — drift check | 22 runs × ~20 s × 1 GB | **$0.01** |
| S3 storage | < 1 GB, mostly Parquet | **$0.02** |
| S3 requests | a few thousand PUT/GET | **$0.01** |
| API Gateway (HTTP) | $1.00 per million | **< $0.01** |
| SNS, SQS, EventBridge, Budgets | all inside the perpetual free tier | **$0.00** |
| CloudWatch logs | 14-day retention, low volume | **$0.03** |
| **Total** | | **≈ $1.60** |

Three quarters of that is CloudWatch — monitoring costs more than the entire
compute and storage of the system it monitors. That is the honest shape of a
small serverless workload, and it is worth saying out loud rather than
rounding away: the custom metrics and alarms could be dropped to bring the bill
under $0.30, and then nobody would find out when the model started drifting.

**What is deliberately absent from that table:** any resource that is billed
while idle. No EC2 instance, no NAT gateway ($32/month), no Real-Time SageMaker
endpoint ($40/month for `ml.m5.large`), no RDS, no MLflow tracking server, no
ALB ($16/month). Each of those was considered and rejected in `decisions.md`,
and together they are the difference between $1.60 and roughly $90.

**The one thing to watch.** The API is public and unauthenticated so that it
can be demonstrated. Throttling is set to 10 requests per second with a burst
of 20, and the Lambda is capped by its own concurrency, so a runaway script
costs cents rather than dollars. For anything beyond a demo, put an API key or
a Cognito authorizer in front of it.

---

## Where the money would go if this grew

The current bill is small because the volume is. The useful question for a
production version is which line item breaks first.

| If this happened | What would dominate | Roughly |
|---|---|---|
| 1,000 predictions/day | Lambda duration, not requests | ~$3/month |
| 100,000 predictions/day | Lambda, and the per-request S3 read (ADR-11) | ~$90/month — at which point precomputed features in DynamoDB (ADR-11, variant B) become the cheaper design |
| Sub-100 ms latency required | Provisioned concurrency, billed hourly whether used or not | ~$15/month per provisioned unit, and the serverless argument collapses |
| Hourly instead of daily data | S3 PUT requests and Parquet file count | Small, but the `raw/` partitioning would need to change to avoid millions of tiny objects |
| A team looking at experiments | An MLflow tracking server on Fargate | ~$15/month, and ADR-9 would have to be reversed |

---

## Tearing it down

```bash
terraform -chdir=infra destroy
```

Two things survive on purpose:

- **The S3 bucket**, if it still holds objects. `force_destroy` is `false`, so
  Terraform refuses rather than silently deleting training data. Empty it
  first if you really mean it:
  `aws s3 rm "s3://$(terraform -chdir=infra output -raw data_bucket)" --recursive`
- **CloudWatch log groups** that have already received events, in some cases.
  Delete them by hand if the account is being cleaned out.

---

## Moving to another account

This is the migration path promised in ADR-8, and it is why account ID, region,
profile and prefix are all variables and none of them is hard-coded.

```bash
terraform -chdir=infra apply \
  -var="profile=my-other-account" \
  -var="region=eu-central-1" \
  -var="project=goldmlops"
```

Steps 1–5 above run again unchanged. What does **not** migrate: CloudWatch
metric history, cost history, the MLflow registry (it lives in the local
SQLite file, so copy `mlflow.db` and `mlartifacts/`), and anything that was
ever created by clicking. Expect one to three hours.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `BucketAlreadyExists` | The bucket name is global, not per account | Change `project`, or import the existing bucket: `terraform import aws_s3_bucket.data <name>` |
| `EntityAlreadyExists` on a role | The role was created by hand earlier | `terraform import aws_iam_role.<name> <role-name>` — this changes nothing in AWS, it only tells Terraform what exists |
| `RequestTimeTooSkewed` on any S3 call | The laptop's clock drifted, usually after sleep | Let macOS resync network time, then retry. S3 allows about 15 minutes of skew |
| `InvalidParameterValueException: image manifest` on Lambda | Image built for the wrong architecture | Rebuild with `--platform linux/arm64` |
| API returns 503 `No model artifact available` | Nothing in `models/current/` | Run step 3 above |
| API returns 422 | A date with no complete feature row — a weekend, or earlier than the data | Omit the date to use the most recent complete day |
| First request takes 20 s | Cold start: 1.6 GB image pull plus model download | Expected. Call `/health` once to warm it before a demo |
| Drift check reports `no reference stored` | No model has been promoted yet, so there is nothing to compare against (ADR-12) | Promote a model, which writes the reference |
| Budget shows $0.00 despite spend | Resources are untagged, or the tag was added after the spend | Cost allocation tags apply going forward only; the tag has to be activated once in Billing settings |
