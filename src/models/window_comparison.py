"""Does a shorter training window produce a better model?

Run with: PYTHONPATH=. .venv/bin/python -m src.models.window_comparison

The EDA showed the market changed regime: 2026 runs at roughly twice the
volatility of the 2016-2024 average. That raises the question this script
answers empirically.

Method: features are always computed on the FULL fetched history, so rolling
windows are complete even at the start of a short window. Only the rows used
for training and evaluation are sliced. Otherwise a two-month window would
lose half its rows to feature warm-up and the comparison would be rigged.
"""
import warnings; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd

from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import root_mean_squared_error, mean_absolute_error

from src.data.fetch import fetch_all
from src.features.pipeline import feature_columns, make_training_frame
from src.models.compare import build_models, baselines, target_series, directional_accuracy

# Trading days per window. Roughly 21 per month.
WINDOWS = {"2 years": 503, "1 year": 252, "6 months": 126, "2 months": 42}

print("Fetching 2y of data (features computed on full history) ...")
frames = fetch_all(period="2y")
frame_full = make_training_frame(frames)
cols = feature_columns(frame_full)
print(f"usable rows after feature warm-up: {len(frame_full)}\n")

def n_splits_for(n_rows: int) -> int:
    """Fewer folds for short windows - otherwise test sets shrink to noise."""
    return max(2, min(5, n_rows // 60))

def evaluate_window(frame: pd.DataFrame, target: str) -> pd.DataFrame:
    X = frame[cols].to_numpy()
    y = target_series(frame, target)
    splits = n_splits_for(len(frame))

    rows = []
    for tr, te in TimeSeriesSplit(n_splits=splits).split(X):
        X_tr, X_te, y_tr, y_te = X[tr], X[te], y[tr], y[te]

        for name, pred in baselines(y_tr, y_te, target).items():
            rows.append({"model": name,
                         "rmse": root_mean_squared_error(y_te, pred),
                         "mae": mean_absolute_error(y_te, pred),
                         "dir_acc": directional_accuracy(y_te, pred) if target == "return" else np.nan})

        for name, model in build_models().items():
            model.fit(X_tr, y_tr)
            pred = model.predict(X_te)
            rows.append({"model": name,
                         "rmse": root_mean_squared_error(y_te, pred),
                         "mae": mean_absolute_error(y_te, pred),
                         "dir_acc": directional_accuracy(y_te, pred) if target == "return" else np.nan})

    summary = pd.DataFrame(rows).groupby("model")[["rmse", "mae", "dir_acc"]].mean()
    ref = summary.loc["baseline_mean", "rmse"]
    summary["vs_baseline_%"] = (1 - summary["rmse"] / ref) * 100
    return summary.sort_values("rmse")


results = {}
for target in ("return", "volatility"):
    print("=" * 78)
    print(f"TARGET: {target}")
    print("=" * 78)

    for label, days in WINDOWS.items():
        frame = frame_full.iloc[-days:] if days < len(frame_full) else frame_full
        splits = n_splits_for(len(frame))
        summary = evaluate_window(frame, target)

        candidates = summary.drop(index=[i for i in summary.index if i.startswith("baseline")])
        best = candidates["rmse"].idxmin()
        margin = summary.loc[best, "vs_baseline_%"]

        results[(target, label)] = {
            "rows": len(frame), "folds": splits, "test_per_fold": len(frame) // (splits + 1),
            "best_model": best, "vs_baseline_%": round(margin, 2),
            "best_rmse": round(summary.loc[best, "rmse"], 6),
            "baseline_rmse": round(summary.loc["baseline_mean", "rmse"], 6),
            "dir_acc": round(summary.loc[best, "dir_acc"], 4) if target == "return" else np.nan,
        }
        flag = "OK " if margin > 0 else "   "
        print(f"{flag}{label:10s} n={len(frame):4d}  folds={splits}  "
              f"best={best:14s} vs baseline {margin:+7.2f}%")
    print()

print("=" * 78)
print("SUMMARY")
print("=" * 78)
out = pd.DataFrame(results).T
out.index.names = ["target", "window"]
print(out.to_string())
