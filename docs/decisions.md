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
