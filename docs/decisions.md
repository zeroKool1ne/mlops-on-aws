# Architecture Decision Records

Every significant design choice in this project, with the alternatives that were
considered, the reasoning, and what the choice costs. A decision without a stated
trade-off is not a decision, it is a preference.

---

## ADR-1 — SageMaker Serverless Inference instead of a Real-Time endpoint

**Chosen:** SageMaker Serverless Inference

**Alternatives:** Real-Time endpoint (persistent instance) · Batch Transform · Asynchronous Inference

**Reasoning.** Predictions are requested sporadically, not continuously. A serverless
endpoint starts on demand and scales back to zero, so only actual compute time is billed.
A Real-Time endpoint on `ml.m5.large` runs around the clock and costs roughly €40 a month
whether or not anyone calls it.

**Trade-off.** Cold starts: the first request after an idle period takes several seconds.
Payload size and memory are capped, and GPUs are not available. For a batch job over
millions of rows, Batch Transform would be the correct choice instead.

**In plain terms.** You pay when you actually ask for a prediction, not for a server
waiting through the night.

---

## ADR-2 — A Lambda facade between API Gateway and the model

**Chosen:** API Gateway → Lambda → SageMaker endpoint

**Alternatives:** Expose the SageMaker endpoint directly · Integrate API Gateway straight onto SageMaker

**Reasoning.** The Lambda is a facade: it validates input, builds features, shapes the
response, and can later take on authentication or caching — none of which requires touching
the model. Calling a SageMaker endpoint directly also requires AWS credentials and SigV4
request signing, which is impractical for external consumers.

**Trade-off.** One more network hop, so slightly higher latency, and one more component to
deploy and monitor.

**In plain terms.** Your application talks to an ordinary web endpoint; whatever model sits
behind it can be replaced without you changing anything.

---

## ADR-3 — S3 as the data store rather than a database

**Chosen:** S3 with Parquet files

**Alternatives:** RDS/PostgreSQL · DynamoDB · Amazon Timestream

**Reasoning.** Market data is append-only time series: no updates, no transactions. Object
storage costs orders of magnitude less than a running database instance, SageMaker reads
training data from S3 natively, and Parquet is columnar and compressed — a good fit for
scanning many rows across few columns.

**Trade-off.** No single-record lookups, no transactions, no secondary indexes. Retrieving
one specific day means reading a file rather than a row. Athena or Glue would have to be
added to run SQL over it.

**In plain terms.** Historical prices are an archive, not a filing cabinet — so we keep them
in cheap object storage instead of an expensive database.

---

## ADR-4 — EventBridge Scheduler instead of cron on EC2

**Chosen:** Amazon EventBridge scheduled rule

**Alternatives:** cron on an EC2 instance · AWS Batch · Step Functions

**Reasoning.** A cron job needs an instance that runs continuously, gets patched and costs
money — for a task that takes two seconds a day. EventBridge is a managed trigger with no
server of its own, built-in retries on failure, and native CloudWatch integration.

**Trade-off.** No state between runs and no complex control flow. As soon as several steps
depend on each other and may fail individually, that logic belongs in Step Functions.

**In plain terms.** The daily data pull happens by itself, with no machine left switched on
to make it happen.

---

## ADR-5 — Terraform as infrastructure-as-code instead of CloudFormation

**Chosen:** Terraform

**Alternatives:** CloudFormation · AWS CDK · AWS SAM · manual console setup

**Reasoning.** Terraform is provider-agnostic and appears far more often in job
specifications. State is explicit, and `terraform plan` shows exactly what will change
before anything does.

**Trade-off.** State has to be managed (remote backend, locking), and Terraform occasionally
lags behind new AWS features. Note that the AWS Solutions Architect exam tests
CloudFormation exclusively — that is studied separately.

**In plain terms.** The whole infrastructure lives as code in the repository: reproducible,
reviewable, and reversible.

---

## ADR-6 — XGBoost as the production model, chosen by comparison

**Chosen:** XGBoost on lag and rolling-window features, selected through a measured comparison

**Alternatives compared:** naive baseline · Ridge/Lasso · Random Forest · XGBoost · LightGBM · optionally LSTM

**Reasoning.** The model is not chosen in advance, it is measured. Every candidate runs
through the same time-series cross-validation (`TimeSeriesSplit`, never shuffled — shuffling
leaks future information into the past) and is scored on RMSE and MAE against the naive
baseline. The expectation is that gradient boosting on well-built lag features wins at this
data volume, because neural networks need substantially more data to pay off. If the
measurement says otherwise, the measurement wins.

**Trade-off.** The comparison costs training time and code complexity. XGBoost itself has no
concept of time — every temporal structure has to be engineered as a feature by hand. In
exchange it trains quickly, needs no GPU, and ships as a built-in SageMaker algorithm.

**In plain terms.** We test several approaches against each other and keep the one that
measurably performs best — not the one that sounds most impressive.

---

## ADR-7 — A naive baseline as the mandatory yardstick

**Chosen:** Naive forecast (yesterday's price) as a required baseline before any model counts

**Alternatives:** Start directly with the complex model · use a moving average as baseline

**Reasoning.** Financial time series are close to a random walk. A model with an impressively
low RMSE is worthless if *"tomorrow equals today"* scores just as well. Without a baseline,
nobody — including the author — can tell whether the model learned anything.

**Trade-off.** It costs time before the interesting work starts, and it frequently delivers
the deflating result that the margin is small. That honesty is the professionally correct
outcome, and it is reported either way.

**In plain terms.** We measure our model against the simplest possible rule. Only if it beats
that rule is it worth anything.

---

## ADR-8 — Deploying into a shared account, with a migration path

**Chosen:** A provided, shared AWS account during development, with a Terraform-driven move to a dedicated account afterwards

**Alternatives:** Build in the private account immediately (no longer free tier, so it costs real money) · run in both in parallel · stay local with no cloud

**Reasoning.** The permissions available in the shared account are sufficient for the whole stack — IAM, SageMaker, Lambda, S3, API Gateway, EventBridge, SNS, ECR, Budgets and CloudWatch were all verified by policy simulation before any work started. The migration stays available at any time because the entire infrastructure is Terraform code with account, region, profile and prefix as variables.

**Trade-off.** A shared account carries unrelated workloads, which has three consequences. Account-level budgets say nothing about this project, so cost tracking has to be filtered by tag. The naming space is shared, so every resource needs a project prefix. And access is temporary, which means the deployed demo does not outlive the engagement. What does not migrate: CloudWatch history, cost history, model registry entries, and anything created by clicking rather than by Terraform. Estimated migration effort: 1–3 hours with clean IaC, 1–2 days without.

**In plain terms.** The solution is not tied to any particular account — it can be rebuilt in any AWS environment in about fifteen minutes.

---

## ADR-9 — MLflow locally rather than a central tracking server

**Chosen:** MLflow with a file-based backend store and S3 as the artifact store; `mlruns/` is synchronised to S3

**Alternatives:** MLflow tracking server on EC2 or Fargate · SageMaker managed MLflow · SageMaker Experiments instead of MLflow · no tracking at all

**Reasoning.** A central tracking server needs a host that runs continuously. That costs money and contradicts the consistently serverless line taken in ADR-4, where even the daily cron job was denied its own server. On a solo project there is no team that needs to look at the same runs, so the main benefit of a server disappears. Comprehensive experiment tracking is achieved just as well locally, as long as artifacts land in S3 and are therefore durable and shareable. MLflow rather than SageMaker Experiments because it is vendor-neutral.

**Trade-off.** SageMaker training jobs run on remote instances and cannot write directly into a local MLflow — metrics have to be collected after the run. The web UI only runs on one machine, so nobody else sees runs live. With a team or parallel experiments, a central server would be the right call.

**In plain terms.** Every training result is recorded and traceable — without another server running around the clock to make that possible.

---

## ADR-10 — Target variable: daily return, not price level

**Chosen:** The model predicts the **return of the next trading day** (percentage change). Directional accuracy is reported alongside it.

**Alternatives:** Next day's closing price (regression on the level) · direction up/down as classification · multi-day horizon

**Reasoning.** Regression on the price level yields an R² around 0.99 — but only because today's price is almost yesterday's price. The model learns nothing about tomorrow, it simply carries the state forward. The metric looks impressive and is worthless. Returns are approximately stationary and force the model to actually predict a change. Directional accuracy is reported as well because it needs no domain knowledge to interpret: "54% of directions are correct" lands with anyone, "RMSE 0.0083" with nobody. The horizon is one trading day because the data is daily and longer horizons would not be defensible at this sample size.

**Trade-off.** Returns are far harder to predict — the numbers will look sober, and the naive baseline may well be hard to beat. That is accepted deliberately: an honest weak result is worth more than an impressive one built on autocorrelation.

**In plain terms.** We predict the change, not the price — because you don't need a model to tell you tomorrow's price is roughly today's.

---

## ADR-11 — Features are computed server-side, not by the caller

**Chosen:** Variant A. The request carries only a date. The predict service loads the required history from S3 and builds features using **the same pipeline as training**.

**Alternatives:** Caller submits ready-made features (the original sketch) · Variant B: a daily job writes features to DynamoDB · Variant C: predictions are precomputed daily and the API only serves them

**Reasoning.** The original sketch had the caller compute features. That does not hold: the model uses lag features and rolling means spanning up to 60 days — history an API consumer does not have and should not need. More importantly, any divergence between the client's computation and the training job's would be **train/serve skew**: in production the model would silently receive systematically different numbers. Variant A solves this by running one shared feature pipeline in both training and serving — shared code, not a second implementation.

**Trade-off.** One S3 read per request, an estimated 100–300 ms of added latency. Irrelevant for a daily forecast, disqualifying for a high-frequency application. At high request volumes Variant B would be correct: a daily job writes finished features into DynamoDB and the service reads a single key.

**In plain terms.** You ask for a date and get a prediction — everything else happens on our side, and demonstrably the same way it happened during training.

---

## ADR-12 — The drift reference is updated only when a model is promoted

**Chosen:** The reference distribution is rewritten only when a new model is **approved** — versioned and timestamped in S3.

**Alternatives:** Update the reference on every training run · rolling reference over the last N days · freeze it once and never change it

**Reasoning.** The reference has to belong to the model currently in production, because drift means precisely "the data has moved away from what *this* model was trained on". Rewriting it on every training run would silently reset the measurement, after which it would never show anything again — a failure that goes unnoticed because the dashboard keeps showing green. A rolling reference has the same problem in slow motion: it chases every change and therefore cannot detect drift by construction. Timestamped versioning also keeps it traceable which reference was used when.

**Trade-off.** After a genuine, lasting market shift the alert persists until a new model is approved, which can produce repeated notifications; the retraining cooldown mitigates that. If no model is promoted for a long time the reference ages and drift scores climb steadily — but that is the correct statement, not a measurement error.

**In plain terms.** We always compare current data against exactly the data the running model learned from — otherwise the monitoring would blind itself.

---

## ADR-13 — FastAPI as a Lambda container instead of a separate predict function

**Chosen:** A single FastAPI application, deployed as a Lambda container image behind API Gateway via the Mangum adapter. The same application serves the web interface, the REST API and the presentation.

**Alternatives:** Separate ZIP Lambda for prediction plus a standalone FastAPI app · FastAPI on ECS/Fargate · a static web page calling API Gateway directly

**Reasoning.** The container is needed regardless: pandas, numpy and xgboost exceed the 250 MB limit of a ZIP Lambda, and Tier 3 requires containerisation. Mangum turns the FastAPI app into a Lambda handler without restructuring, which leaves **one** codebase that runs locally under uvicorn, ships to ECR as a container image, and serves requests behind API Gateway on AWS. Two separate applications for the same prediction logic would mean duplicated maintenance and a second source of divergence. It also allows the presentation to be delivered as a scrollable page with the live demo embedded — one URL instead of slides plus a terminal.

**Trade-off.** Container Lambdas have slower cold starts than ZIP Lambdas, an estimated one to several seconds extra; the endpoint is warmed once before the demo. It also ties the presentation to application availability, so the page is built to print cleanly and a PDF is kept as a fallback. Under sustained high load, Fargate would be the more appropriate runtime.

**In plain terms.** The same application runs on the laptop, in the container and in the cloud — there is only one version to maintain.
