"""SageMaker evaluation entry point (Processing Job).

Separate from training on purpose. The model registry's approval gate reads the
metrics this script writes, so evaluation has to be a step of its own that can
fail, be inspected, and be re-run without retraining.

What it enforces (ADR-7): a model is only worth promoting if it beats the naive
baseline. The verdict is written into the metrics file, not decided here - this
script measures, the pipeline decides.

Runs unchanged in both places:

    local     python -m src.models.evaluate --model-dir artifacts --fetch-if-missing
    SageMaker Processing Job with /opt/ml/processing/* paths
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, root_mean_squared_error

# A model must beat the incumbent by this much before promotion is justified.
# Below it, the improvement is smaller than the variation between CV folds and
# therefore indistinguishable from chance.
MIN_IMPROVEMENT_PCT = 2.0

HOLDOUT_DAYS = 126


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--model-dir", default=os.environ.get("SM_MODEL_DIR", "artifacts"))
    p.add_argument("--data-dir", default="data")
    p.add_argument("--output-dir", default="artifacts")
    p.add_argument("--holdout-days", type=int, default=HOLDOUT_DAYS)
    p.add_argument("--fetch-if-missing", action="store_true")
    return p.parse_args()


def directional_accuracy(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    mask = y_true != 0
    if mask.sum() == 0:
        return float("nan")
    return float(np.mean(np.sign(y_pred[mask]) == np.sign(y_true[mask])))


def main() -> None:
    from src.models.train import (METADATA_FILENAME, MODEL_FILENAME, build_target,
                                  load_training_frame)

    args = parse_args()

    model_dir = Path(args.model_dir)
    model = joblib.load(model_dir / MODEL_FILENAME)
    metadata = json.loads((model_dir / METADATA_FILENAME).read_text())

    target = metadata["target"]
    features = metadata["feature_columns"]
    print(f"evaluating target={target} on the last {args.holdout_days} trading days")

    frame = load_training_frame(args.data_dir, args.fetch_if_missing)
    holdout = frame.iloc[-args.holdout_days:]

    X = holdout[features].to_numpy()
    y_true = build_target(holdout, target)
    y_pred = model.predict(X)

    # Baselines. For returns "tomorrow equals today" is a return of zero; for
    # volatility zero would be absurd, so the mean is the naive forecast.
    baseline = (np.zeros_like(y_true) if target == "return"
                else np.full_like(y_true, build_target(frame.iloc[:-args.holdout_days], target).mean()))

    model_rmse = root_mean_squared_error(y_true, y_pred)
    baseline_rmse = root_mean_squared_error(y_true, baseline)
    improvement = (1 - model_rmse / baseline_rmse) * 100

    metrics = {
        "target": target,
        "holdout_window": [str(holdout.index[0].date()), str(holdout.index[-1].date())],
        "n_holdout_rows": int(len(holdout)),
        "model": {
            "rmse": float(model_rmse),
            "mae": float(mean_absolute_error(y_true, y_pred)),
            # Meaningless for volatility: it is non-negative, so the sign always matches.
            "directional_accuracy": (float(directional_accuracy(y_true, y_pred))
                                     if target == "return" else None),
        },
        "baseline": {
            "rmse": float(baseline_rmse),
            "mae": float(mean_absolute_error(y_true, baseline)),
        },
        "improvement_over_baseline_pct": float(improvement),
        "min_improvement_required_pct": MIN_IMPROVEMENT_PCT,
        "beats_baseline": bool(improvement > 0),
        "meets_promotion_threshold": bool(improvement >= MIN_IMPROVEMENT_PCT),
    }

    # SageMaker Model Quality metrics live in a nested "regression_metrics" block;
    # keeping that shape means the file can be attached to the model package as-is.
    metrics["regression_metrics"] = {
        "rmse": {"value": float(model_rmse)},
        "mae": {"value": float(metrics["model"]["mae"])},
    }

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "evaluation.json").write_text(json.dumps(metrics, indent=2))

    print(json.dumps({k: v for k, v in metrics.items() if k != "regression_metrics"}, indent=2))
    print(f"\nwrote {out_dir / 'evaluation.json'}")

    if not metrics["meets_promotion_threshold"]:
        print(f"\nNOT promotable: {improvement:+.2f}% is below the "
              f"{MIN_IMPROVEMENT_PCT}% threshold. The incumbent model stays live.")


if __name__ == "__main__":
    main()
