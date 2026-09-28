"""Classical time-series candidates: ARIMA and Prophet.

Kept separate from the tabular models in `compare.py` because they work on the
raw series rather than on engineered features, and because both need a rolling
origin to be evaluated fairly.

That fairness point matters. Both of these models are often evaluated by fitting
once and forecasting an entire test period - hundreds of days ahead - while the
tabular models only ever predict one day ahead. That is a handicap, not a
comparison. Here both are refitted at every step and asked for one day only.

Run with:
    PYTHONPATH=. .venv/bin/python -m src.models.classical
"""

from __future__ import annotations

import logging
import warnings

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, root_mean_squared_error

warnings.filterwarnings("ignore")
logging.getLogger("prophet").setLevel(logging.ERROR)
logging.getLogger("cmdstanpy").setLevel(logging.ERROR)

TEST_DAYS = 126          # the same holdout length used elsewhere
ARIMA_MAX_ORDER = 3


def directional_accuracy(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    mask = y_true != 0
    if mask.sum() == 0:
        return float("nan")
    return float(np.mean(np.sign(y_pred[mask]) == np.sign(y_true[mask])))


def score(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, float]:
    return {
        "rmse": root_mean_squared_error(y_true, y_pred),
        "mae": mean_absolute_error(y_true, y_pred),
        "dir_acc": directional_accuracy(y_true, y_pred),
    }


# --------------------------------------------------------------------------
# ARIMA
# --------------------------------------------------------------------------

def select_arima_order(returns: np.ndarray) -> tuple[int, int, int]:
    """Grid search over (p, 0, q) by AIC.

    d = 0 because returns are already stationary - ADF and KPSS agree on that
    (see notebooks/01_eda.ipynb). ARIMA(p,0,q) on returns is equivalent to
    ARIMA(p,1,q) on the price level.
    """
    from statsmodels.tsa.arima.model import ARIMA

    best_aic, best_order = np.inf, (1, 0, 0)
    for p in range(ARIMA_MAX_ORDER + 1):
        for q in range(ARIMA_MAX_ORDER + 1):
            if p == 0 and q == 0:
                continue
            try:
                aic = ARIMA(returns, order=(p, 0, q)).fit().aic
                if aic < best_aic:
                    best_aic, best_order = aic, (p, 0, q)
            except Exception:
                continue
    return best_order


def run_arima(returns: pd.Series, test_days: int = TEST_DAYS) -> tuple[np.ndarray, np.ndarray]:
    """Rolling one-step-ahead forecast of the return series.

    Parameters are estimated once per run and then carried forward with
    `append(refit=False)`: the model sees every new observation, but the
    coefficients are not re-estimated at every step. Refitting fully each day
    would take hours and change nothing material.
    """
    from statsmodels.tsa.arima.model import ARIMA

    y = returns.to_numpy()
    split = len(y) - test_days
    order = select_arima_order(y[:split])
    print(f"  selected order: ARIMA{order}")

    res = ARIMA(y[:split], order=order).fit()
    preds = []
    for actual in y[split:]:
        preds.append(res.forecast(steps=1)[0])
        res = res.append([actual], refit=False)

    return np.array(preds), y[split:]


# --------------------------------------------------------------------------
# Prophet
# --------------------------------------------------------------------------

def run_prophet(close: pd.Series, test_days: int = TEST_DAYS) -> tuple[np.ndarray, np.ndarray]:
    """Rolling one-step-ahead forecast, refitted at every step.

    Prophet models a level, so its price forecast is converted into an implied
    return against the last ACTUAL close. Anchoring on the real price is
    generous to Prophet - its own error does not compound - which makes a poor
    result here all the more conclusive.
    """
    from prophet import Prophet

    df = pd.DataFrame({"ds": close.index, "y": close.to_numpy()}).reset_index(drop=True)
    split = len(df) - test_days

    preds_price, prev_close, actual_price = [], [], []
    for i in range(split, len(df) - 1):
        model = Prophet(daily_seasonality=False, weekly_seasonality=True,
                        yearly_seasonality=True, changepoint_prior_scale=0.05)
        model.fit(df.iloc[: i + 1])

        preds_price.append(model.predict(df.iloc[[i + 1]][["ds"]])["yhat"].iloc[0])
        prev_close.append(df.iloc[i]["y"])
        actual_price.append(df.iloc[i + 1]["y"])

        if (i - split + 1) % 25 == 0:
            print(f"  {i - split + 1}/{test_days - 1} steps")

    preds_price = np.array(preds_price)
    prev_close = np.array(prev_close)
    actual_price = np.array(actual_price)

    pred_return = (preds_price - prev_close) / prev_close
    true_return = (actual_price - prev_close) / prev_close

    price_rmse = root_mean_squared_error(actual_price, preds_price)
    naive_rmse = root_mean_squared_error(actual_price, prev_close)
    print(f"  on the price level: Prophet {price_rmse:.2f} USD vs naive {naive_rmse:.2f} USD")

    return pred_return, true_return


# --------------------------------------------------------------------------

def main() -> None:
    from src.data.fetch import fetch_all
    from src.features.pipeline import align_panel

    print("Downloading market data ...")
    panel = align_panel(fetch_all(period="10y"))
    close = panel["gold_close"].dropna()
    returns = close.pct_change().dropna()

    rows = []

    print("\nARIMA (rolling one-step-ahead) ...")
    arima_pred, arima_true = run_arima(returns)
    rows.append({"model": "arima", **score(arima_true, arima_pred)})
    rows.append({"model": "baseline_zero", **score(arima_true, np.zeros_like(arima_true))})
    rows.append({"model": "baseline_mean",
                 **score(arima_true, np.full_like(arima_true, arima_true.mean()))})

    print("\nProphet (rolling one-step-ahead, refit each step) ...")
    prophet_pred, prophet_true = run_prophet(close)
    rows.append({"model": "prophet", **score(prophet_true, prophet_pred)})

    summary = pd.DataFrame(rows).set_index("model").sort_values("rmse")
    reference = summary.loc["baseline_zero", "rmse"]
    summary["vs_baseline_%"] = (1 - summary["rmse"] / reference) * 100

    print("\n=== Classical candidates, target = next-day return ===")
    print(summary.to_string(float_format=lambda v: f"{v:10.5f}"))


if __name__ == "__main__":
    main()
