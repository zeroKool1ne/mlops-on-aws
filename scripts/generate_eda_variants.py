"""Generate EDA notebooks for different time windows.

Same structure as 01_eda.ipynb, parameterised by observation window. Building
them from one generator guarantees they stay comparable - if the analysis
differs, it is because the data differs, not because the code does.
"""
import json, pathlib

CONFIGS = [
    {
        "fname": "02_eda_2y.ipynb",
        "title": "Last Two Years (2025-2026)",
        "fetch_period": "2y",
        "window_days": None,          # analyse everything that was fetched
        "holdout_days": 42,           # ~2 months
        "short_sample": False,
    },
    {
        "fname": "03_eda_1m.ipynb",
        "title": "Last Month",
        "fetch_period": "1y",         # fetch a year so features are computable
        "window_days": 21,            # but analyse only the last ~21 trading days
        "holdout_days": 21,
        "short_sample": True,
    },
]


def build(cfg):
    cells = []

    def md(text):
        cells.append({"cell_type": "markdown", "metadata": {},
                      "source": [l + "\n" for l in text.strip().split("\n")]})

    def code(text):
        cells.append({"cell_type": "code", "execution_count": None, "metadata": {},
                      "outputs": [], "source": [l + "\n" for l in text.strip().split("\n")]})

    window_note = (
        f"Data is fetched over **{cfg['fetch_period']}** so that rolling features remain "
        f"computable, but the analysis window is the **last {cfg['window_days']} trading days**."
        if cfg["window_days"] else
        f"Observation window: **{cfg['fetch_period']}**."
    )

    md(f"""
# Gold/USD — Exploratory Data Analysis — {cfg['title']}

**Ironhack Final Project 2 — ML on Cloud**

Same analysis as `01_eda.ipynb`, run over a different observation window. Generated
from the same code, so any difference in the results comes from the data, not from
the method.

{window_note}

**Why look at a shorter window at all.** The ten-year analysis found a regime
change: 2026 runs at roughly twice the volatility of the 2016-2024 average, and 21
of 29 features differ significantly between the training period and the holdout.
That raises a concrete question — is a model trained on ten years learning from a
market that no longer exists?
""")

    if cfg["short_sample"]:
        md("""
> ### ⚠️ Read the sample size before reading the results
>
> This notebook analyses roughly **21 observations**. Several of the statistics
> below are reported for completeness but are **not interpretable** at that sample
> size:
>
> | Statistic | Why it fails here |
> |---|---|
> | ACF / PACF | the 95% white-noise band widens to about ±0.43 — almost nothing can reach it |
> | ADF / KPSS | both need substantially more observations; p-values are unreliable |
> | Ljung-Box at long lags | undefined or meaningless when the lag count approaches the sample size |
> | Skew / kurtosis | dominated by single observations |
>
> What **is** meaningful at this size: the price path, the current volatility level,
> and the drift comparison against the preceding months. Read those, ignore the rest.
""")

    code("""
import sys, warnings
from pathlib import Path

warnings.filterwarnings("ignore")

ROOT = Path.cwd().parent if Path.cwd().name == "notebooks" else Path.cwd()
sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

from statsmodels.tsa.stattools import adfuller, kpss, acf, pacf
from statsmodels.graphics.tsaplots import plot_acf, plot_pacf
from statsmodels.stats.diagnostic import acorr_ljungbox

sns.set_theme(style="whitegrid")
plt.rcParams["figure.figsize"] = (12, 4)
plt.rcParams["axes.titlesize"] = 12

pd.set_option("display.width", 120)
pd.set_option("display.float_format", lambda v: f"{v:,.5f}")
""")

    code(f"""
# --- window configuration for this notebook -------------------------------
FETCH_PERIOD = "{cfg['fetch_period']}"
WINDOW_DAYS  = {cfg['window_days']!r}     # None = use everything fetched
HOLDOUT_DAYS = {cfg['holdout_days']}

print(f"fetch period : {{FETCH_PERIOD}}")
print(f"analysis     : {{'last ' + str(WINDOW_DAYS) + ' trading days' if WINDOW_DAYS else 'full fetched period'}}")
""")

    md("""
## 1. Loading the data

Identical set of instruments as in the ten-year notebook: gold as the target, plus
dollar index, oil, S&P 500 and VIX as explanatory markets.
""")

    code("""
from src.data.fetch import fetch_all, TICKERS

frames = fetch_all(period=FETCH_PERIOD)

overview = pd.DataFrame({
    name: {"ticker": TICKERS[name], "rows": len(df),
           "from": df.index[0].date(), "to": df.index[-1].date()}
    for name, df in frames.items()
}).T
overview
""")

    code("""
from src.features.pipeline import align_panel

full_panel = align_panel(frames)

# The analysis window. Features were computed on the full fetched history,
# so rolling windows are complete even at the start of the window.
panel = full_panel.iloc[-WINDOW_DAYS:] if WINDOW_DAYS else full_panel

print(f"full fetched   : {len(full_panel)} rows   {full_panel.index[0].date()} to {full_panel.index[-1].date()}")
print(f"analysis window: {len(panel)} rows   {panel.index[0].date()} to {panel.index[-1].date()}")
""")

    md("""
## 2. Data quality
""")

    code("""
gold_days = set(frames["gold"].index)
for name in ["dxy", "oil", "sp500", "vix"]:
    missing = len(gold_days - set(frames[name].index))
    print(f"{name:6s}: {missing:4d} gold trading days without an own observation "
          f"({missing / len(gold_days):.1%})")

print()
print("NaNs after forward-fill:")
print(panel.isna().sum().to_string())
""")

    md("""
## 3. The price level
""")

    code("""
fig, axes = plt.subplots(3, 2, figsize=(14, 9))
for ax, name in zip(axes.flat, ["gold", "dxy", "oil", "sp500", "vix"]):
    col = f"{name}_close"
    if col in panel:
        panel[col].plot(ax=ax, linewidth=1.1)
        ax.set_title(name.upper())
        ax.set_xlabel("")
axes.flat[-1].axis("off")
plt.tight_layout()
plt.show()
""")

    code("""
gold_period = panel["gold_close"]
print(f"start  : {gold_period.iloc[0]:,.1f}")
print(f"end    : {gold_period.iloc[-1]:,.1f}")
print(f"change : {(gold_period.iloc[-1] / gold_period.iloc[0] - 1):+.2%}")
print(f"min/max: {gold_period.min():,.1f} / {gold_period.max():,.1f}")
""")

    md("""
## 4. Stationarity

**ADF** — null: unit root (non-stationary). `p < 0.05` → stationary.
**KPSS** — null: stationary. `p < 0.05` → non-stationary.
""")

    code("""
price = panel["gold_close"].dropna()
returns = price.pct_change().dropna()
abs_returns = returns.abs()

def safe_tests(series, name):
    \"\"\"Both tests, degrading gracefully when the sample is too small.\"\"\"
    row = {"series": name, "n": len(series)}
    try:
        stat, p, *_ = adfuller(series, autolag="AIC")
        row |= {"ADF_stat": stat, "ADF_p": p,
                "ADF_verdict": "stationary" if p < 0.05 else "NON-stationary"}
    except Exception as exc:
        row |= {"ADF_stat": np.nan, "ADF_p": np.nan, "ADF_verdict": f"n/a ({type(exc).__name__})"}
    try:
        stat, p, *_ = kpss(series, regression="c", nlags="auto")
        row |= {"KPSS_stat": stat, "KPSS_p": p,
                "KPSS_verdict": "NON-stationary" if p < 0.05 else "stationary"}
    except Exception as exc:
        row |= {"KPSS_stat": np.nan, "KPSS_p": np.nan, "KPSS_verdict": f"n/a ({type(exc).__name__})"}
    return row

pd.DataFrame([
    safe_tests(price, "gold price level"),
    safe_tests(returns, "gold returns"),
    safe_tests(abs_returns, "absolute returns"),
]).set_index("series")
""")

    md("""
## 5. Distribution of returns
""")

    code("""
fig, axes = plt.subplots(1, 3, figsize=(14, 3.5))

axes[0].plot(returns.index, returns.values, linewidth=0.8, marker="o", markersize=2)
axes[0].set_title("Daily returns over time")

sns.histplot(returns, bins=min(40, max(8, len(returns) // 3)), kde=len(returns) > 30, ax=axes[1])
axes[1].set_title("Distribution of returns")

from scipy import stats
stats.probplot(returns, dist="norm", plot=axes[2])
axes[2].set_title("Q-Q plot against a normal distribution")

plt.tight_layout()
plt.show()

print(f"n          : {len(returns)}")
print(f"mean       : {returns.mean():+.6f}   ({returns.mean() * 252:+.2%} annualised)")
print(f"std        : {returns.std():.6f}    ({returns.std() * np.sqrt(252):.2%} annualised)")
print(f"skew       : {returns.skew():+.4f}")
print(f"kurtosis   : {returns.kurtosis():+.4f}")
print(f"share up   : {(returns > 0).mean():.4f}")
""")

    md("""
## 6. Autocorrelation — is there anything to predict?
""")

    code("""
max_lags = min(30, max(1, len(returns) // 3))
ci = 1.96 / np.sqrt(len(returns))

fig, axes = plt.subplots(1, 2, figsize=(14, 3.5))
plot_acf(returns, lags=max_lags, ax=axes[0], title="ACF — returns")
plot_pacf(returns, lags=min(max_lags, len(returns) // 2 - 1), ax=axes[1],
          title="PACF — returns", method="ywm")
plt.tight_layout()
plt.show()

n_show = min(10, max_lags)
a = acf(returns, nlags=n_show, fft=True)
p_ = pacf(returns, nlags=min(n_show, len(returns) // 2 - 1))
tbl = pd.DataFrame({
    "ACF": a[1:n_show + 1].round(4),
    "PACF": np.pad(p_[1:], (0, max(0, n_show - len(p_) + 1)),
                   constant_values=np.nan)[:n_show].round(4),
}, index=pd.RangeIndex(1, n_show + 1, name="lag"))
tbl["significant"] = ["yes" if abs(v) > ci else "-" for v in tbl["ACF"]]
print(f"95% white-noise band: +/- {ci:.4f}   (n = {len(returns)})")
tbl
""")

    code("""
lags = [l for l in (5, 10, 20) if l < len(returns) // 2]
if lags:
    print("Ljung-Box, joint test across lags:")
    print(acorr_ljungbox(returns, lags=lags, return_df=True).round(6))
else:
    print(f"Sample too small for a Ljung-Box test (n = {len(returns)}).")
""")

    md("""
## 7. Volatility clustering
""")

    code("""
fig, axes = plt.subplots(1, 2, figsize=(14, 3.5))
plot_acf(abs_returns, lags=max_lags, ax=axes[0], title="ACF — absolute returns")

window = 20 if len(full_panel) > 60 else 5
full_panel["gold_close"].pct_change().rolling(window).std().tail(
    len(panel) * 3 if WINDOW_DAYS else len(full_panel)
).plot(ax=axes[1], linewidth=1.0, title=f"{window}-day rolling volatility")
plt.tight_layout()
plt.show()

aa = acf(abs_returns, nlags=n_show, fft=True)
pd.DataFrame({
    "ACF returns": a[1:n_show + 1].round(4),
    "ACF abs returns": aa[1:n_show + 1].round(4),
    "abs significant": ["yes" if abs(v) > ci else "-" for v in aa[1:n_show + 1]],
}, index=pd.RangeIndex(1, n_show + 1, name="lag"))
""")

    code("""
if lags:
    lb_ret = acorr_ljungbox(returns, lags=[max(lags)], return_df=True)
    lb_abs = acorr_ljungbox(abs_returns, lags=[max(lags)], return_df=True)
    print(f"Ljung-Box across lags 1-{max(lags)}")
    print(f"  returns          stat = {lb_ret['lb_stat'].iloc[0]:8.2f}   p = {lb_ret['lb_pvalue'].iloc[0]:.6f}")
    print(f"  absolute returns stat = {lb_abs['lb_stat'].iloc[0]:8.2f}   p = {lb_abs['lb_pvalue'].iloc[0]:.6f}")
else:
    print("Sample too small for a Ljung-Box test.")
""")

    md("""
## 8. External markets
""")

    code("""
ret_panel = pd.DataFrame({
    name: panel[f"{name}_close"].pct_change()
    for name in ["gold", "dxy", "oil", "sp500", "vix"] if f"{name}_close" in panel
}).dropna()

fig, axes = plt.subplots(1, 2, figsize=(14, 4))
sns.heatmap(ret_panel.corr(), annot=True, fmt=".2f", cmap="RdBu_r", center=0,
            ax=axes[0], cbar=False)
axes[0].set_title("Same-day correlation of returns")

lagged = pd.DataFrame({f"{c}_t-1": ret_panel[c].shift(1)
                       for c in ret_panel.columns if c != "gold"})
lagged["gold_t"] = ret_panel["gold"]
sns.heatmap(lagged.corr()[["gold_t"]].drop("gold_t"), annot=True, fmt=".3f",
            cmap="RdBu_r", center=0, ax=axes[1], cbar=False)
axes[1].set_title("Yesterday's move vs today's gold return")
plt.tight_layout()
plt.show()
""")

    md(f"""
## 9. Drift — has the most recent period moved away from what came before?

The last **{cfg['holdout_days']} trading days** are compared against everything
before them, using the same PSI and KS implementation that the production drift
Lambda uses.
""")

    code("""
from src.features.pipeline import feature_columns, make_training_frame
from src.monitoring.drift import compare

frame = make_training_frame(frames)          # built on the FULL fetched history
cols = feature_columns(frame)

reference_frame = frame.iloc[:-HOLDOUT_DAYS]
recent_frame = frame.iloc[-HOLDOUT_DAYS:]

n, m = len(reference_frame), len(recent_frame)
d_crit = 1.36 * np.sqrt((n + m) / (n * m))

print(f"Reference : {reference_frame.index[0].date()} to {reference_frame.index[-1].date()}  ({n} rows)")
print(f"Recent    : {recent_frame.index[0].date()} to {recent_frame.index[-1].date()}  ({m} rows)")
print(f"\\nKS critical value at alpha = 0.05: D = {d_crit:.4f}")

drift = compare(reference_frame, recent_frame, cols)
print(f"Features above it: {(drift['ks_stat'] > d_crit).sum()} of {len(drift)}")
print(f"\\nPSI verdicts:\\n{drift['verdict'].value_counts().to_string()}")
drift.head(12)
""")

    code("""
vol = full_panel["gold_close"].pct_change().rolling(20).std()
by_month = vol.groupby([vol.index.year, vol.index.month]).mean()
by_month.index = [f"{y}-{m:02d}" for y, m in by_month.index]

ax = by_month.plot(kind="bar", figsize=(12, 3.2),
                   title="Mean 20-day volatility per month")
ax.axhline(by_month.mean(), color="crimson", linestyle="--", label="period mean")
ax.legend()
plt.tight_layout()
plt.show()
by_month.round(5)
""")

    md(f"""
## 10. Comparison against the ten-year analysis

Put the numbers from this notebook next to those from `01_eda.ipynb`. What differs
is the answer to the question that motivated this exercise: **is a shorter training
window the better basis for the model?**

Reference values from the ten-year notebook:

| Measure | Ten years (2016-2026) |
|---|---|
| Returns: significant ACF lags (of 10) | 2 |
| Ljung-Box returns, lags 1-10 | p = 0.023 |
| Absolute returns: significant ACF lags | 10 of 10 |
| Ljung-Box absolute returns | p < 0.000001 |
| Annualised volatility | 16.96% |
| Annualised mean return | +13.20% |
| Excess kurtosis | 7.56 |
| Skew | −0.57 |

Read the corresponding values above and note where they diverge. A materially
different volatility level or autocorrelation structure is direct evidence for
shortening the training window.
""")

    return {
        "cells": cells,
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python", "version": "3.13"},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }


for cfg in CONFIGS:
    nb = build(cfg)
    out = pathlib.Path("notebooks") / cfg["fname"]
    out.write_text(json.dumps(nb, indent=1))
    print(f"wrote {out}  ({len(nb['cells'])} cells)")
