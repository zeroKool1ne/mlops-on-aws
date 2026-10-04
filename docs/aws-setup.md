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

Two numbers, because they answer two questions:

| | |
|---|---|
| **Measured today** | **$0.04 a month** — what the deployed resources have actually used |
| **Projected** | **≈ $1.40 a month** — the finished architecture, running daily |

Most of the gap is monitoring that does not exist yet. Both numbers are
reproducible at any time:

```bash
python scripts/cost-report.py          # measured, from the resources themselves
python scripts/cost-report.py --json   # same, machine-readable
```

### The breakdown

List prices for `us-east-1`, checked October 2026 (the date is in
`scripts/cost-report.py`, because a cost model with undated prices cannot be
checked later). Volume assumes 22 trading days a month.

| Service | What drives it | Measured | Projected |
|---|---|---|---|
| CloudWatch — custom metrics | 3 metrics × $0.30 | $0.00 — none exist | **$0.90** |
| CloudWatch — alarms | 4 alarms × $0.10 | $0.00 — none exist | **$0.40** |
| ECR storage | 0.349 GiB of unique layers × $0.10/GB | **$0.0349** | $0.0349 |
| CloudWatch logs | 14-day retention, low volume | $0.0000003 | ~$0.03 |
| Lambda — ingestion | 22 runs × 7 s billed × 2 GB, arm64 | $0.0011 | $0.0041 |
| Lambda — API | a few hundred invocations | not deployed | ~$0.02 |
| Lambda — drift check | 22 runs × ~20 s × 1 GB | not deployed | ~$0.01 |
| S3 storage | Parquet, current and noncurrent versions | $0.0001 | $0.0003 |
| S3 requests | ~130 PUT a month | < $0.01 | < $0.01 |
| API Gateway (HTTP) | $1.00 per million | not deployed | < $0.01 |
| EventBridge Scheduler | 14 M invocations free each month | $0.00 | $0.00 |
| SNS, SQS | inside the perpetual free tier | $0.00 | $0.00 |
| **Total** | | **$0.036** | **≈ $1.40** |

Two thirds of the projected bill is CloudWatch: **the monitoring costs more
than the compute and storage of the system it monitors, by a factor of
thirty.** That is the honest shape of a small serverless workload, and it is
worth saying rather than rounding away. Dropping the custom metrics and alarms
would bring the bill under $0.10 — and then nobody would find out when the
model started drifting. The monitoring is not overhead on the system; at this
size it *is* the system's running cost.

### How this is measured, and why not with Cost Explorer

Development runs in a shared course account. Cost Explorer there reports the
whole cohort's spend, which is both none of this project's business and the
wrong question — it cannot say what *this* costs. So nothing above comes from a
bill. Each resource's usage is read and priced directly, which is also the only
method that works before the first invoice exists.

**Lambda is exact, not approximated.** Every invocation writes a `REPORT` line
carrying its billed duration and configured memory:

```
REPORT RequestId: 666ac0c7…  Billed Duration: 7003 ms  Memory Size: 2048 MB
```

That is precisely what AWS charges on, so parsing those lines reconstructs the
bill rather than estimating it. It also makes the two cost drivers visible
separately: billed duration includes the init phase for container images (a
4.3 s import of pandas and scikit-learn, charged on every cold start), which
would be invisible in a per-request estimate.

**Memory is not the figure to minimise.** The ingestion peaks at 291 MB of the
2048 MB configured, which looks like sevenfold over-provisioning and is not:
memory also sets the CPU share, and billing is GB-seconds — memory × time. More
memory at a shorter runtime often costs the same or less. Right-sizing a Lambda
means testing that product, not measuring peak memory.

**ECR image sizes must not be added up.** `imageSizeInBytes` counts every layer
an image references, so summing it across images multiplies whatever they
share — and images built from the same source share nearly everything. This
repository holds four images:

| | Tag | `imageSizeInBytes` |
|---|---|---|
| OCI image index (rejected by Lambda) | — | 374 MB |
| its arm64 manifest | — | 374 MB |
| its attestation manifest | — | 1.4 kB |
| the Docker V2 manifest in use | `latest` | 374 MB |

Summed: 1.046 GiB, $0.105 a month. Actually stored: **13 unique layers,
0.349 GiB, $0.035 a month** — a threefold difference. `cost-report.py` walks
the manifests and collects layer digests into a set rather than adding the
sizes. The same content-addressing that makes a second `docker push` fast makes
the naive sum wrong.

Three of those four images are debris from a build that had BuildKit
provenance enabled, and the lifecycle rule (`imageCountMoreThan: 10`) will not
reach them. A second rule for untagged images would; failed builds produce them
routinely.

### What is deliberately absent

Any resource billed while idle. No EC2 instance, no NAT gateway ($32/month),
no Real-Time SageMaker endpoint ($40/month for `ml.m5.large`), no RDS, no
MLflow tracking server, no ALB ($16/month). Each was considered and rejected in
`decisions.md`; together they are the difference between $1.40 and roughly $90.

### The one thing to watch

The API is public and unauthenticated so that it can be demonstrated.
Throttling is set to 10 requests per second with a burst of 20, and the Lambda
is capped by its own concurrency, so a runaway script costs cents rather than
dollars. For anything beyond a demo, put an API key or a Cognito authorizer in
front of it.

### Keeping an eye on it

```bash
python scripts/cost-report.py        # what this project costs
./scripts/cost-check.sh              # what of this project is running
```

`cost-check.sh` has two flags that are off by default, both because the account
is shared: `--spend` reports the account-wide bill, and `--all-resources`
inventories every billable resource in it — which shows other participants'
clusters and load balancers by name. Use either only on an account you own.

Tags (`Project=goldmlops`) are what make the filtered inventory work. They do
**not** make costs appear per project in the console: that needs cost
allocation tags activated, which is a payer-level setting on an account that is
not ours. Hence the local calculation.

### The budget alarm does not work here, and that is worth knowing

`infra/budget.tf` filters on `TagKeyValue = user:Project$goldmlops`, which is
the right design: an account-level budget on a shared account says nothing
about this project. But a budget can only filter on a tag that has been
**activated as a cost allocation tag**, and that is the payer-level setting
above. Unactivated, the filter matches nothing, the budget stays at $0.00
forever and never fires.

So the seatbelt is bolted in but not fastened, and it fails in the worst
direction: silently, and looking exactly like "nothing has gone wrong yet".
On an account where the tag can be activated, it works as written; here,
`cost-report.py` is the substitute, and it has to be run rather than waited
for.

The limit is also worth a second look independently of that. At $20 against a
projected $1.40 it catches an accidental NAT gateway or a Real-Time endpoint,
which is the point — but not a tenfold overrun. Two thresholds, say $5 and
$20, would separate "this is wrong" from "this is catastrophic".

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
