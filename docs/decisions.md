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

**Chosen:** MLflow with a **SQLite** backend store and S3 as the artifact store — a local file on disk, not a running service

**Alternatives:** MLflow tracking server on EC2 or Fargate · SageMaker managed MLflow · SageMaker Experiments instead of MLflow · the plain `mlruns/` file store · no tracking at all

**Reasoning.** A central tracking server needs a host that runs continuously. That costs money and contradicts the consistently serverless line taken in ADR-4, where even the daily cron job was denied its own server. On a solo project there is no team that needs to look at the same runs, so the main benefit of a server disappears. Comprehensive experiment tracking is achieved just as well locally, as long as artifacts land in S3 and are therefore durable and shareable. MLflow rather than SageMaker Experiments because it is vendor-neutral.

**Amended during implementation.** This decision originally specified the plain `mlruns/` file store. That turned out to be wrong on two counts, and both were only visible once the code ran. MLflow 3 puts the filesystem backend into maintenance mode and raises an exception unless it is explicitly opted back into. More decisively, **the Model Registry has never worked on the file store at all** — it requires a database backend. Since the promotion gate in this project *is* a registry alias, the file store could not have delivered what this ADR promises. SQLite is the smallest thing that satisfies the requirement, and it changes nothing about the argument above: it is a single file on disk, so there is still no server running around the clock. The migration path to a real server is one environment variable, `MLFLOW_TRACKING_URI`.

**Trade-off.** SQLite serialises writes, so genuinely parallel training runs would contend on the database — irrelevant for one run a day, disqualifying for a team running sweeps. SageMaker training jobs run on remote instances and cannot write directly into a local MLflow — metrics have to be collected after the run. The web UI only runs on one machine, so nobody else sees runs live. With a team or parallel experiments, a central server would be the right call.

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

---

## ADR-14 — The drift threshold is measured, not borrowed

**Chosen:** Each feature carries its own PSI noise floor, measured walk-forward on the training data. A feature is flagged when its live PSI exceeds a multiple of **its own** floor — not when it exceeds a universal 0.25.

**Alternatives:** The conventional fixed PSI thresholds of 0.10 / 0.25 · a wider comparison window · fewer histogram bins · drop PSI and monitor prediction error instead · no drift monitoring

**Reasoning.** The 0.10 / 0.25 thresholds come from credit scoring, where the monitored quantity is an independent draw per customer. Almost nothing here is. `gold_vol20` is a 20-day rolling standard deviation, so two consecutive values share nineteen of their twenty observations and are nearly identical. A one-year window of it contains on the order of a dozen independent observations, not 250. PSI assumes independent samples; fed overlapping ones, it reports its own variance as a finding.

This was not a theoretical worry. It was found by a test written against the real feature set, and the numbers are unambiguous. Measured on data where nothing has broken:

| Feature | Noise floor (95th pct) |
|---|---|
| `gold_vol20` | 3.62 |
| `gold_vol10` | 2.26 |
| `gold_vol5` | 0.78 |
| `gold_ret_lag3` | 0.23 |
| `dxy_ret` | 0.18 |

The floors span 0.176 to 4.769 — a factor of 27 between features in the same model. **For 20 of the 27 monitored features, the conventional 0.25 threshold sits *below* the level that feature produces when nothing has happened at all.** Deployed as originally specified, this monitor would have raised a significant-drift alarm on its first run and every run after it, forever, and the one real alarm would have been indistinguishable from the twenty fake ones.

Two further defects were found and fixed at the same time:

- **Calendar features had to be excluded entirely.** `month` is a deterministic function of the date. Any window shorter than a year covers part of the year against a reference covering all of it, which scored a PSI around 9.0 — permanently. Drift in the calendar is not a finding, it is arithmetic.
- **The floor has to be measured walk-forward.** The obvious method — slide a window through the reference period and score each position against the full reference — underestimates it, because those windows helped form the reference distribution and are therefore unfairly easy. The live window never is: it is always the period after the reference ends. Measuring in-sample gave a floor of 0.28 for `gold_vol20` where the honest walk-forward figure is 3.62, a thirteen-fold difference, and the calibration still cried wolf until this was corrected.

**Trade-off.** Three real costs. The floors are estimated from overlapping windows, so they are an estimate and not a confidence bound — the percentile is indicative. A feature whose normal behaviour is genuinely erratic gets a high floor and therefore a high bar, so a real shift in it is detected later than in a quiet feature; that is the correct trade for alert fatigue, but it is a trade. And the reference is now more expensive to build, because every feature needs a walk-forward sweep rather than a single histogram.

**What would be better.** PSI on engineered features is a proxy for the thing that actually matters, which is whether predictions have got worse. Here the labels arrive with a one-day lag, so prediction error *could* be monitored directly — that is strictly the stronger signal and the right next step. It is not in this version because it needs prediction history accumulated over months, and this project is three weeks old.

**In plain terms.** We measured how much our own alarm goes off when nothing is wrong, and set it above that. The standard threshold everyone quotes would have made it ring every single day.

---

## ADR-15 — Serving runs in the API Lambda; the SageMaker endpoint stays designed, not deployed

**Chosen:** The prediction request is answered inside the API Lambda, which loads `model.tar.gz` from S3 once per cold start and predicts in-process. SageMaker Serverless Inference (ADR-1) remains the designed production path and is selected by setting `SAGEMAKER_ENDPOINT`; it is not provisioned.

**Alternatives:** Provision Serverless Inference on a managed scikit-learn container · provision it on a custom container (BYOC) · retrain the model inside whichever scikit-learn version the managed container offers · remove the SageMaker path from the design entirely

**Reasoning.** The model artifact is a pickle, and `requirements-api.txt` pins scikit-learn to the exact version that wrote it, with a comment explaining why: unpickling an estimator under a different version is a documented source of silently wrong predictions — wrong answers, not errors. SageMaker's managed scikit-learn containers track their own release schedule and do not generally offer the current version, so the managed route forces a choice between an unpinned unpickle and retraining inside their version. Retraining there would mean the numbers in this repository were produced by one library version and served by another, which is exactly the inconsistency the pin exists to prevent.

That leaves a custom container, which is a real option and the right one eventually. It is not a one-day option: a SageMaker serving container has its own contract (`/ping`, `/invocations`, port 8080) that the Lambda runtime interface does not satisfy, so it is a second image with a second build and a second thing to keep in step with the first.

Against that, measured: the Lambda path answers a cold request in **2.1 s** and a warm one in **0.5 s**, against API Gateway's 30 s ceiling. At this volume the endpoint would buy no latency and no throughput — it would buy a second place where the model can be stale and a second cold start in front of the first.

**Trade-off.** Four real costs, and the first two are the ones that would decide this differently at scale.

- **Serving cannot scale separately from the API.** One Lambda concurrency limit now governs both request handling and model execution. With a real traffic pattern these want different limits.
- **No data capture.** SageMaker endpoints log request/response pairs to S3 as a built-in; here that would have to be written by hand. That is the input the drift monitor would most like to have (ADR-14 says prediction-error monitoring is the stronger signal, and this is how you would feed it).
- **The model has to fit in a Lambda.** 290 KB today against a 10 GB image limit, so this is not binding — but it is a ceiling that the endpoint does not have.
- **The project cannot claim SageMaker serving.** The architecture diagrams mark the endpoint `(planned)` rather than implying it runs.

**What would be better.** Build one image that satisfies both contracts — the Lambda runtime interface and SageMaker's HTTP contract — from the same `src/`, so there is still one codebase and one dependency set. Then provision the endpoint, set `SAGEMAKER_ENDPOINT`, and turn on data capture. `serving.py` already branches on that variable, so the switch costs no code change; the work is entirely in the image and the provisioning.

**In plain terms.** The model is pinned to a library version that AWS's ready-made container does not offer, and building our own container is a day's work that buys no speed at this size. So the model runs inside the API itself, the switch to move it is already in the code, and the diagram says `(planned)` instead of pretending.
