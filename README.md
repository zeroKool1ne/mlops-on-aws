# Gold/USD Price Forecasting — End-to-End MLOps on AWS

![Status](https://img.shields.io/badge/status-deployed-brightgreen)
![Tests](https://img.shields.io/badge/tests-55%20passing-brightgreen)
![Python](https://img.shields.io/badge/python-3.13-blue)
![AWS](https://img.shields.io/badge/AWS-SageMaker%20%7C%20Lambda%20%7C%20API%20Gateway-orange)
![IaC](https://img.shields.io/badge/IaC-Terraform-purple)
![License](https://img.shields.io/badge/license-MIT-green)

> A production-shaped machine learning system that ingests Gold/USD market data daily,
> trains and versions a forecasting model, serves predictions through a REST API, and
> retrains itself when the incoming data drifts away from what it was trained on.

**Ironhack Data Science & AI — Final Project 2 (ML on Cloud).**
Built solo · Presentation: 5 October 2026

---

## Table of contents

- [Why this project](#why-this-project)
- [Architecture](#architecture)
- [Results](#results)
- [Getting started](#getting-started)
- [Project structure](#project-structure)
- [Documentation](#documentation)
- [Cost](#cost)
- [Credits](#credits)
- [License](#license)

---

## Why this project

Gold is a benchmark hedge against inflation and uncertainty, and its USD price moves with
currency strength, energy prices, equity sentiment and market volatility. Forecasting it is
a genuinely hard problem — financial series sit close to a random walk, which makes it an
honest test of whether a model has learned anything at all.

That honesty is the point of this project. Every model here is measured against a naive
baseline (*"tomorrow equals today"*). A model that cannot beat that baseline is reported as
not beating it.

The engineering goal is the other half: getting a model from a notebook into something that
runs on a schedule, serves requests, watches itself, and can be rebuilt from source by
someone who has never seen it.

## Architecture

![Architecture overview](docs/diagrams/01_architecture_overview.png)

**The API is deployed and running.** Its URL is available on request rather than
printed here: the endpoint is public and unauthenticated so that it can be
demonstrated, and AWS has no hard spending cap — only rate limits and alarms. A
published URL is an open invitation that cannot be withdrawn once it is in a
commit. A live demonstration, a demo page and the generated `/docs` are a
message away.

What a call looks like:

```bash
curl -s -X POST "$API_URL/predict" \
  -H 'content-type: application/json' -d '{"date": "2026-10-02"}'
```

```json
{"feature_date": "2026-10-02", "current_price": 4162.30,
 "predicted_volatility": 0.007961, "predicted_move_usd": 33.14,
 "served_by": "local", "latency_ms": 527}
```

Everything also runs locally with no AWS account at all — see
[Getting started](#getting-started).

Components marked **(planned)** on the diagrams are designed and not provisioned — the
training job, the model registry, the SageMaker endpoint (ADR-15), the drift Lambda and
its alarms, and the GitHub Actions pipeline. Ingestion, the data lake, the registry
bucket, the image, the API and its gateway are deployed and can be called. The design is
unchanged; the diagrams simply say which half of it currently runs, because an
architecture picture that does not is claiming more than it should.

The system separates into two paths that run on completely different clocks. Keeping them
apart is the central design decision:

### Training path — offline, daily or when drift is detected

![Training path](docs/diagrams/02_training_path.png)

EventBridge triggers a Lambda that pulls market data into S3 as Parquet. A SageMaker
Training Job builds features, trains the model and evaluates it. Parameters, metrics and
artifacts are logged to MLflow; the model itself is versioned in the SageMaker Model
Registry. A new model is only promoted if it beats the incumbent **and** the baseline.

### Inference path — online, per request, in milliseconds

![Inference path](docs/diagrams/03_inference_path.png)

A request reaches API Gateway, is validated and turned into features by a Lambda facade,
and is answered by a SageMaker Serverless Inference endpoint. No training happens here.

The facade exists so the public contract stays stable while the model behind it changes,
and so callers do not need AWS credentials to get a prediction.

### Architecture decisions

Every significant choice is recorded with its alternatives, its reasoning and its cost in
[`docs/decisions.md`](docs/decisions.md) — including the ones where the trade-off is
genuinely uncomfortable.

The diagrams above are generated from [`docs/diagrams/architecture.py`](docs/diagrams/architecture.py),
so they are versioned alongside the code rather than drifting away from it:

```bash
cd docs/diagrams && ../../.venv/bin/python architecture.py
```

## Results

Two questions were asked of the same data, the same features and the same
validation protocol. One has a usable answer and one does not, and both are
reported.

### Protocol

The last **126 trading days** (2026-04-02 to 2026-10-01) were set aside and
touched once, at the very end. Everything before that was used for
walk-forward cross-validation with `TimeSeriesSplit`, five folds, never
shuffled — shuffling would train on the future and test on the past, which
inflates every metric it touches. 2,493 rows, 29 features, ten years of data.

Every candidate is scored against a **naive baseline**. For returns that is a
forecast of exactly zero (*"tomorrow equals today"*), the strongest naive
forecast there is for a near-random walk. For volatility it is the mean
volatility seen during training, because zero would be absurd — markets always
move.

### Can we predict *which way* gold moves tomorrow? No.

Cross-validated; lower RMSE is better:

| Model | RMSE | MAE | Directional accuracy | vs baseline |
|---|---|---|---|---|
| **baseline (zero)** | 0.01064 | 0.00761 | 54.6 % | — |
| random forest | 0.01073 | 0.00771 | 49.3 % | **−0.80 %** |
| ridge | 0.01094 | 0.00792 | 51.3 % | −2.81 % |
| XGBoost | 0.01104 | 0.00797 | 50.5 % | −3.76 % |
| LightGBM | 0.01105 | 0.00801 | 49.7 % | −3.81 % |

**Not one of the four beats doing nothing.** Directional accuracy sits between
49 % and 51 % — a coin flip. The baseline's 54.6 % is not skill either: it
predicts the mean, the mean is positive, and gold rose over the period, so
"always up" happened to be right 54.6 % of the time.

This is the result ADR-10 predicted and accepted in advance: *an honest weak
result is worth more than an impressive one built on autocorrelation.*
Regressing on the price level instead would have produced an R² near 0.99 and
meant nothing, because today's price is almost yesterday's price.

### Can we predict *how violently* it moves tomorrow? Yes, modestly.

| Model | RMSE | MAE | vs baseline |
|---|---|---|---|
| **random forest** | **0.00745** | 0.00511 | **+3.51 %** |
| XGBoost | 0.00758 | 0.00534 | +1.77 % |
| LightGBM | 0.00771 | 0.00535 | +0.07 % |
| baseline (mean) | 0.00772 | 0.00517 | — |
| ridge | 0.00787 | 0.00539 | −1.98 % |

Random forest wins and clears the 2 % promotion gate. On the untouched
holdout:

| | Model | Baseline | Difference |
|---|---|---|---|
| **RMSE** | 0.009580 | 0.009866 | **+2.90 %** |
| **MAE** | 0.007551 | 0.007166 | **−5.38 %** |

**Those two disagree, and that matters.** The model makes *fewer large misses*
at the cost of a *larger typical error*. For a volatility forecast that is the
trade worth making — the day the model calls quiet and the market is not is the
day that costs money — so the promotion gate decides on RMSE. But it is a real
blind spot: nothing in the gate would stop a model making that trade far too
aggressively, so the gate now states the disagreement out loud instead of
reporting a clean win.

### What the model actually uses

Three importance measures, because each answers a different question:

| Feature | mean \|SHAP\| | Direction | Permutation |
|---|---|---|---|
| `gold_vol20` | 0.00154 | +0.90 | −0.00006 |
| `gold_range` | 0.00100 | +0.91 | −0.00012 |
| `gold_vol10` | 0.00061 | +0.84 | −0.00005 |
| `gold_ret_mean20` | 0.00035 | +0.76 | −0.00003 |
| `vix_vol10` | 0.00020 | +0.52 | +0.00005 |

The top three are all *"how much has gold been moving lately"*, each with a
direction near +0.9: high recent volatility raises the forecast. That is
**volatility clustering** — a real, long-documented market property, and
reassuring to find rather than something exotic.

But **permutation importance is negative for almost every feature**: shuffling
them does not make holdout predictions worse. SHAP says the model leans hard on
past volatility; permutation says removing it barely hurts. They disagree, and
that is consistent with a model beating the baseline by three percent rather
than thirty. Computing only one measure would have hidden it.

![SHAP attribution](artifacts/explain/shap_beeswarm.png)

### What this is worth

A 3 % RMSE improvement over "assume average volatility" is small. It is also
real, measured on data the model never saw, and reported together with the
metric that disagrees. The engineering around it — scheduled ingestion, a
versioned registry with a promotion gate, a calibrated drift monitor, a
deployed API — is what this project is actually about. A pipeline that can
honestly tell you the model is barely better than nothing is worth more than
one that cannot tell.

## Getting started

### Prerequisites

- Python 3.13
- An AWS account with credentials configured (`aws configure`)
- Terraform ≥ 1.15 (for the infrastructure)
- Docker (for the containerised model)
- Graphviz (`brew install graphviz`, only needed to regenerate diagrams)

### Local setup

```bash
git clone https://github.com/zeroKool1ne/mlops-on-aws.git
cd mlops-on-aws
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Running the API locally

```bash
python -m src.models.train --target volatility --fetch-if-missing
uvicorn src.api.main:app --reload
```

Then open <http://127.0.0.1:8000> for the demo page, or
<http://127.0.0.1:8000/docs> for the generated API documentation.

```bash
curl -s -X POST localhost:8000/predict \
  -H 'content-type: application/json' -d '{"date": "2026-09-30"}'
```

No AWS account is needed for this. `src/api/serving.py` loads the model into
the process when `SAGEMAKER_ENDPOINT` is unset and forwards to the endpoint
when it is set — the same code either way.

### Running the tests

```bash
pytest -q        # 55 tests, no network access required
```

The suite is deliberately offline: `yfinance` is an unofficial scraper with no
SLA, so a suite that depends on it fails for reasons unrelated to the code. The
tests that matter check properties rather than execution — that a feature row
does not change when future rows are removed (no leakage), that training and
serving produce identical features for the same day (no train/serve skew), and
that the drift detector stays quiet on data where nothing happened.

### Reproducing the results above

```bash
python -m src.models.compare                           # four algorithms, both targets
python -m src.models.evaluate --fetch-if-missing        # holdout metrics, registers the model
python -m src.models.explain --fetch-if-missing         # SHAP and permutation importance
mlflow ui --backend-store-uri sqlite:///mlflow.db       # every run, every metric
```

## Project structure

```
.
├── src/
│   ├── api/           # FastAPI app, demo page, Lambda handler, serving backends
│   ├── data/          # ingestion: fetch + validate -> S3 Parquet
│   ├── features/      # the one feature pipeline, shared by training and serving
│   ├── models/        # train, evaluate, compare, explain, tracking + registry
│   └── monitoring/    # drift detection and the scheduled check
├── notebooks/         # exploratory data analysis (10y, 2y, 1m windows)
├── infra/             # Terraform: all 46 AWS resources
├── docs/
│   ├── decisions.md   # 15 architecture decision records
│   ├── model-card.md  # what the model is, and is not, for
│   ├── aws-setup.md   # deployment, cost, teardown, troubleshooting
│   └── diagrams/      # architecture diagrams as code
├── artifacts/         # model, metrics, SHAP output, drift reference
├── tests/             # 55 tests, offline by design
├── Dockerfile         # one arm64 image, three Lambda handlers
└── requirements-api.txt   # runtime deps only, pinned to match training
```

## Documentation

| Document | Contents |
|---|---|
| [Architecture decisions](docs/decisions.md) | All 15 design choices, their alternatives and their trade-offs — including the two that turned out wrong and had to be amended |
| [Model card](docs/model-card.md) | Metrics, intended use, limitations, and what this model must not be used for |
| [AWS setup guide](docs/aws-setup.md) | Deployment from scratch, verification, measured cost estimate, teardown, troubleshooting |
| API reference | Generated from the code, served at `/docs` on the running API |

## Cost

**$0.47 a month measured, ≈$1.40 projected** for the finished architecture.
Both are reproducible:

```bash
python scripts/cost-report.py
```

The measured figure is what the deployed resources have actually used; the
projected one includes the monitoring that is not built yet. The projection
named four alarms at $0.10 as its largest line, and the day they were created
they became the largest line in the measurement too — which is the most useful
thing a cost model can do. Full breakdown and
method in [`docs/aws-setup.md`](docs/aws-setup.md#what-it-costs).

Nothing here reads a bill. Each resource's usage is measured and priced against
the published rates — Lambda exactly, from the `Billed Duration` and
`Memory Size` in every `REPORT` line, which is what AWS charges on. That also
keeps the calculation honest about where the money goes: **two thirds of the
projected bill is CloudWatch.** The monitoring costs thirty times the compute
and storage of the system it monitors, which is the shape of a small serverless
workload rather than a mistake. Dropping the metrics and alarms would get under
$0.10, and then nobody would find out when the model started drifting.

One number worth keeping: ECR image sizes cannot be added up. Four images in
the registry report 1.046 GiB between them and occupy 0.349 GiB, because images
built from the same source share nearly all their layers and each layer is
stored once. The same content-addressing that makes a second `docker push` fast
makes the naive sum wrong by threefold.

What is deliberately absent: no EC2 instance, no NAT gateway ($32/month), no
Real-Time SageMaker endpoint ($40/month), no RDS, no load balancer, no MLflow
tracking server. Each was considered and rejected in
[`docs/decisions.md`](docs/decisions.md); together they are the difference
between $1.40 and roughly $90.

## Credits

- **Data:** [Yahoo Finance](https://finance.yahoo.com/) via the [`yfinance`](https://github.com/ranaroussi/yfinance) package
- **Course:** [Ironhack](https://www.ironhack.com/) Data Science & AI bootcamp
- **Diagrams:** [`diagrams`](https://diagrams.mingrammer.com/) by mingrammer, using official AWS architecture icons

## License

Released under the MIT License — see [LICENSE](LICENSE).

---

**Disclaimer:** This project is an educational exercise in machine learning engineering.
Nothing here is investment advice, and the model's predictions should not be used to make
financial decisions.
