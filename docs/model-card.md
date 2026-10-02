# Model card — Gold/USD next-day volatility

| | |
|---|---|
| **Name** | `gold-volatility`, version 1, alias `champion` |
| **Task** | Regression. Forecast the absolute return of gold for the next trading day |
| **Model** | `RandomForestRegressor` — 300 trees, max depth 6, min 20 samples per leaf, seed 42 |
| **Chosen by** | Comparison against ridge, XGBoost and LightGBM on walk-forward CV (see [Results](../README.md#results)) |
| **Trained on** | 2,367 rows, 2016-11-01 to 2026-04-01 |
| **Evaluated on** | 126 trading days, 2026-04-02 to 2026-10-01, untouched during selection |
| **Features** | 29, built by `src/features/pipeline.py` |
| **Libraries** | scikit-learn 1.9.1, pandas 3.0.6, numpy 2.5.3 — pinned, because a pickle loaded under a different version is a documented source of silently wrong predictions |
| **Licence** | MIT |
| **Updated** | 2026-10-02 |

---

## What it predicts, precisely

The **absolute value of tomorrow's gold return** — how far the price will move,
not which way. Expressed in return units: `0.0075` means an expected move of
about 0.75 %, which at a gold price of $4,188 is roughly **$31**.

It does **not** predict direction. That was tried, measured and rejected: see
[*Can we predict which way gold moves tomorrow? No*](../README.md#can-we-predict-which-way-gold-moves-tomorrow-no).
Four algorithms all failed to beat a naive baseline, with directional accuracy
between 49 % and 51 %. The code still supports the `return` target so the
negative result stays reproducible, but no return model is promoted or served.

## Why absolute return as the volatility proxy

Absolute return is the standard proxy for realised volatility: drop the
direction, keep the magnitude. Alternatives considered were squared returns
(which over-weight single large days) and a rolling standard deviation as the
target (which smooths the thing being predicted and makes the task artificially
easy by giving the model 19 of its own 20 inputs).

## Intended use

Built as a **teaching and engineering exercise**: an end-to-end MLOps pipeline
with a genuinely hard problem at its centre, so that the honesty of the
evaluation is tested rather than assumed.

Legitimate uses:

- Demonstrating a production-shaped ML system end to end
- A reference for how to report a weak-but-real result
- A baseline for anyone attempting the same forecast better

## Out of scope — do not use this for

- **Trading or investment decisions of any kind.** A 3 % RMSE improvement over
  "assume average volatility" has no economic value after costs.
- **Risk limits, margin calculation, or position sizing.** Under-forecast
  volatility is exactly the failure that bankrupts a book, and this model
  under-forecasts the typical day (see MAE below).
- **Options pricing.** Implied volatility from the options market is a better
  forecast than this and is directly observable.
- **Any horizon except one trading day.** The data is daily and the sample size
  does not support longer horizons.
- **Any instrument except gold in USD.**

---

## Performance

On the 126-day holdout, never used for selection:

| Metric | Model | Naive baseline | Difference |
|---|---|---|---|
| RMSE | 0.009580 | 0.009866 | **+2.90 %** |
| MAE | 0.007551 | 0.007166 | **−5.38 %** |

Cross-validated over five walk-forward folds, random forest beat the baseline
on RMSE by **+3.51 %**; XGBoost by 1.77 %, LightGBM by 0.07 %, ridge by −1.98 %.

The naive baseline is the **mean training volatility** — "tomorrow will be as
volatile as an average day". Zero would be absurd for volatility, because
markets always move.

### The two metrics disagree, and this is the most important line in this card

RMSE is **better** by 2.9 %; MAE is **worse** by 5.4 %. RMSE punishes large
errors quadratically, MAE treats all errors alike. A model better on RMSE and
worse on MAE is making **fewer large misses at the cost of a larger typical
error**.

For a volatility forecast that is the correct trade — the day the model calls
quiet and the market is not is the day that costs money — so the promotion gate
decides on RMSE. But the gate is **blind to how far that trade goes**: nothing
in it would stop a model that gained 1 % of RMSE while doubling MAE. The gate
therefore states the disagreement explicitly rather than reporting a clean win.
Anyone who needs accuracy on a typical day should not use this model.

### What it actually learned

| Feature | mean \|SHAP\| | Direction | Permutation |
|---|---|---|---|
| `gold_vol20` | 0.00154 | +0.90 | −0.00006 |
| `gold_range` | 0.00100 | +0.91 | −0.00012 |
| `gold_vol10` | 0.00061 | +0.84 | −0.00005 |
| `gold_ret_mean20` | 0.00035 | +0.76 | −0.00003 |
| `vix_vol10` | 0.00020 | +0.52 | +0.00005 |

The top features are all measures of *how much gold has been moving lately*,
each pushing the forecast in the same direction it moves: **volatility
clustering**, a real and long-documented market property. Finding it is
reassuring — the model learned something true about markets rather than an
artefact of the sample.

**But permutation importance is negative for nearly every feature.** Shuffling
them does not make holdout predictions worse. SHAP says the model leans hard on
past volatility; permutation says removing it barely hurts out of sample. Both
are correct, and together they say the signal is thin — which is exactly
consistent with a 3 % improvement rather than a 30 % one.

---

## Limitations

**The problem is close to unpredictable.** Financial series sit near a random
walk. This was the point of choosing it, and the result reflects it.

**One instrument, one horizon, one regime.** Trained on 2016–2026, a decade
containing COVID, a rate-hike cycle and a gold bull run — but one decade.

**Data provenance is weak.** `yfinance` is an unofficial scraper of Yahoo
Finance: no SLA, no guarantees, and it breaks without notice. Every download is
validated (`src/data/fetch.py` raises rather than warns), but a systematic
change in Yahoo's adjustment methodology would pass validation and shift the
features.

**External markets are lagged by a day.** Gold futures, equities and oil close
at different times, so a one-day lag is applied rather than reasoning about
timezones. This costs some signal and removes a whole class of look-ahead bug.

**No uncertainty estimate.** A point forecast with no interval. For a volatility
model that is a real gap: the most useful output would be a prediction
interval, and quantile regression would be the obvious next step.

**Drift detection is a proxy.** The monitor watches the input distribution, not
prediction error. Labels arrive with a one-day lag here, so error *could* be
monitored directly, and that would be the stronger signal — see
[ADR-14](decisions.md#adr-14--the-drift-threshold-is-measured-not-borrowed).

**Monitoring thresholds are calibrated, not derived.** The noise floors are
estimated from overlapping windows, so they are indicative rather than
confidence bounds.

---

## Fairness and bias

No personal data is involved, and no individual or group is scored, ranked or
affected. The usual fairness analysis does not apply: there are no protected
attributes and no human subjects.

The biases that do exist are statistical, and they matter for anyone who
mistakes this for a usable forecast:

- **Survivorship and regime bias.** Ten years of one bull-leaning decade. A
  model fitted to it will under-forecast volatility in a crisis regime it has
  never seen.
- **Recency bias in the features.** Rolling windows of 5–20 days mean the model
  extrapolates the recent past. It will be systematically late to a regime
  change — exactly when a volatility forecast matters most.
- **Western market hours.** The explanatory markets (DXY, S&P 500, WTI, VIX)
  are US-centric. Asian trading sessions enter only indirectly.
- **Metric bias toward large moves.** As above: optimising RMSE makes the model
  systematically worse on ordinary days.

---

## Reproducing this

```bash
pip install -r requirements.txt
python -m src.models.compare                       # the model selection above
python -m src.models.train --target volatility --fetch-if-missing
python -m src.models.evaluate --fetch-if-missing   # metrics, registration, promotion
python -m src.models.explain --fetch-if-missing    # SHAP and permutation importance
mlflow ui --backend-store-uri sqlite:///mlflow.db
```

Every run records the git commit, whether the working tree was dirty, and the
scikit-learn, pandas and numpy versions — the two things most often left out,
and the two without which a number cannot be traced back to its code or rerun.

Data is fetched live, so re-running on a later date gives a later window and
slightly different numbers. The figures in this card are from **2026-10-02**,
git `3281648`.

## Promotion and retirement

A model becomes `champion` only if it beats the naive baseline on RMSE by at
least 2 % on the holdout. Both gates are enforced in
`src/models/tracking.py::promotion_decision`; the 2 % margin exists so that
noise between random seeds does not fill the registry with versions nobody
chose. Rejected candidates are still registered — a rejected model is evidence
that a decision was made, and deleting it hides that.

This version should be retired when any of the following is true: a drift
alarm fires and is confirmed as a genuine regime change, a candidate beats it on
both RMSE *and* MAE, or a prediction-error monitor replaces the input-drift
proxy.
