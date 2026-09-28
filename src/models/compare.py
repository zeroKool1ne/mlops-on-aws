"""Model comparison for both prediction targets.

Two questions are asked of the same data:

    return      - which way does gold move tomorrow?
    volatility  - how violently does it move tomorrow?

They share everything: features, candidate models, validation protocol. The
only difference is one line in `target_series`. That is deliberate - it makes
the comparison between the two honest, because nothing else varies.

Protocol:
  * The last HOLDOUT_DAYS trading days are set aside and touched exactly once,
    at the very end. Everything before that is used for walk-forward CV.
  * TimeSeriesSplit only, never shuffled. Shuffling would train on the future
    and test on the past, inflating every metric.
  * Every candidate is scored against a naive baseline. A model that cannot
    beat the baseline has learned nothing (ADR-7).
"""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, root_mean_squared_error
from sklearn.model_selection import TimeSeriesSplit
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

warnings.filterwarnings("ignore")

HOLDOUT_DAYS = 126   # roughly six months, never used for model selection
N_SPLITS = 5
SEED = 42

TARGETS = ("return", "volatility")


# --------------------------------------------------------------------------
# targets
# --------------------------------------------------------------------------

def target_series(frame: pd.DataFrame, target: str) -> np.ndarray:
    """The one line that separates the two questions."""
    if target == "return":
        return frame["target_return"].to_numpy()
    if target == "volatility":
        # Absolute return is the standard proxy for realised volatility:
        # drop the direction, keep the magnitude.
        return frame["target_return"].abs().to_numpy()
    raise ValueError(f"unknown target: {target}")


# --------------------------------------------------------------------------
# metrics
# --------------------------------------------------------------------------

def directional_accuracy(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Share of days where the predicted sign matches the actual sign.

    Flat days are dropped - there is no direction to get right. A prediction of
    exactly zero counts as wrong, which is the honest treatment: it expresses
    no view. Only meaningful for the return target.
    """
    mask = y_true != 0
    if mask.sum() == 0:
        return float("nan")
    return float(np.mean(np.sign(y_pred[mask]) == np.sign(y_true[mask])))


def evaluate(y_true: np.ndarray, y_pred: np.ndarray, target: str) -> dict[str, float]:
    scores = {
        "rmse": root_mean_squared_error(y_true, y_pred),
        "mae": mean_absolute_error(y_true, y_pred),
    }
    # Direction is meaningless for volatility - it is non-negative by definition.
    scores["dir_acc"] = directional_accuracy(y_true, y_pred) if target == "return" else np.nan
    return scores


# --------------------------------------------------------------------------
# candidates
# --------------------------------------------------------------------------

def build_models() -> dict[str, object]:
    """Candidates, cheapest first. Scaling only matters for the linear model."""
    from lightgbm import LGBMRegressor
    from xgboost import XGBRegressor

    return {
        "ridge": Pipeline([
            ("scale", StandardScaler()),
            ("model", Ridge(alpha=1.0)),
        ]),
        "random_forest": RandomForestRegressor(
            n_estimators=300, max_depth=6, min_samples_leaf=20,
            random_state=SEED, n_jobs=-1,
        ),
        "xgboost": XGBRegressor(
            n_estimators=300, max_depth=4, learning_rate=0.03,
            subsample=0.8, colsample_bytree=0.8,
            random_state=SEED, n_jobs=-1, verbosity=0,
        ),
        "lightgbm": LGBMRegressor(
            n_estimators=300, max_depth=4, learning_rate=0.03,
            subsample=0.8, colsample_bytree=0.8,
            random_state=SEED, n_jobs=-1, verbose=-1,
        ),
    }


def baselines(y_train: np.ndarray, y_test: np.ndarray, target: str) -> dict[str, np.ndarray]:
    """The yardsticks every candidate has to beat.

    For returns, "tomorrow equals today" means a return of exactly zero - the
    strongest naive forecast there is for a near-random walk. For volatility,
    zero would be absurd (markets always move), so the naive forecast is the
    average volatility seen during training.
    """
    if target == "return":
        return {
            "baseline_zero": np.zeros_like(y_test),
            "baseline_mean": np.full_like(y_test, y_train.mean()),
        }
    return {"baseline_mean": np.full_like(y_test, y_train.mean())}


# --------------------------------------------------------------------------
# evaluation
# --------------------------------------------------------------------------

def cross_validate(frame: pd.DataFrame, feature_cols: list[str], target: str) -> pd.DataFrame:
    """Walk-forward evaluation of every candidate plus the baselines."""
    X = frame[feature_cols].to_numpy()
    y = target_series(frame, target)

    rows: list[dict] = []

    for fold, (train_idx, test_idx) in enumerate(TimeSeriesSplit(n_splits=N_SPLITS).split(X), 1):
        X_train, X_test = X[train_idx], X[test_idx]
        y_train, y_test = y[train_idx], y[test_idx]

        for name, prediction in baselines(y_train, y_test, target).items():
            rows.append({"fold": fold, "model": name, **evaluate(y_test, prediction, target)})

        for name, model in build_models().items():
            model.fit(X_train, y_train)
            rows.append({"fold": fold, "model": name,
                         **evaluate(y_test, model.predict(X_test), target)})

    return pd.DataFrame(rows)


def summarise(results: pd.DataFrame) -> pd.DataFrame:
    """Average over folds and express every model relative to the baseline."""
    summary = results.groupby("model")[["rmse", "mae", "dir_acc"]].mean().sort_values("rmse")
    reference = summary.loc["baseline_mean", "rmse"]
    summary["vs_baseline_%"] = (1 - summary["rmse"] / reference) * 100
    return summary


def run_target(frame: pd.DataFrame, feature_cols: list[str], target: str) -> pd.DataFrame:
    print(f"\n{'=' * 64}")
    print(f"TARGET: {target}")
    print("=" * 64)

    summary = summarise(cross_validate(frame, feature_cols, target))
    print(summary.to_string(float_format=lambda v: f"{v:10.5f}"))

    candidates = summary.drop(index=[i for i in summary.index if i.startswith("baseline")])
    best = candidates["rmse"].idxmin()
    margin = summary.loc[best, "vs_baseline_%"]

    print(f"\nBest candidate : {best}")
    print(f"Beats baseline : {'YES' if margin > 0 else 'NO'}  ({margin:+.2f}%)")
    return summary


def main() -> None:
    from src.data.fetch import fetch_all
    from src.features.pipeline import feature_columns, make_training_frame

    print("Downloading market data ...")
    frames = fetch_all(period="10y")

    print("Building features ...")
    frame = make_training_frame(frames)
    feature_cols = feature_columns(frame)

    train_frame = frame.iloc[:-HOLDOUT_DAYS]
    holdout_frame = frame.iloc[-HOLDOUT_DAYS:]

    print(f"\nRows total     : {len(frame)}")
    print(f"Features       : {len(feature_cols)}")
    print(f"CV period      : {train_frame.index[0].date()} to {train_frame.index[-1].date()}")
    print(f"Holdout        : {holdout_frame.index[0].date()} to {holdout_frame.index[-1].date()}"
          f"  ({len(holdout_frame)} days, untouched)")

    for target in TARGETS:
        run_target(train_frame, feature_cols, target)

    print("\nRMSE and MAE are in return units: 0.01 = one percent.")
    print("dir_acc 0.50 = coin flip; it is undefined for volatility.")


if __name__ == "__main__":
    main()
