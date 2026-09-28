"""SageMaker training entry point.

Trains exactly one model and writes the artifact. Model *selection* happened
once in `compare.py`; this script is the production step that runs over and
over, so it deliberately does not compare anything.

Runs unchanged in both places (ADR-13, one code path):

    local     python -m src.models.train --target volatility --data-dir data/
    SageMaker the estimator calls this file as the container entry point

SageMaker conventions used here:
  SM_CHANNEL_TRAIN  input data directory
  SM_MODEL_DIR      where the artifact must be written
  SM_OUTPUT_DATA_DIR  where side outputs go
"""

from __future__ import annotations

import argparse
import json
import os
import tarfile
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

MODEL_FILENAME = "model.joblib"
METADATA_FILENAME = "metadata.json"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()

    # What to predict. See ADR-10 for why returns rather than price level.
    p.add_argument("--target", choices=["return", "volatility"], default="volatility")

    # Hyperparameters. SageMaker passes these as command line arguments.
    p.add_argument("--n-estimators", type=int, default=300)
    p.add_argument("--max-depth", type=int, default=6)
    p.add_argument("--min-samples-leaf", type=int, default=20)
    p.add_argument("--random-state", type=int, default=42)

    # Rows held back so that evaluate.py scores on data the model never saw.
    # Set to 0 when training the final production model on everything.
    p.add_argument("--holdout-days", type=int, default=126)

    # Paths. The SM_* defaults are what SageMaker sets inside the container;
    # locally they fall back to plain directories.
    p.add_argument("--model-dir", default=os.environ.get("SM_MODEL_DIR", "artifacts"))
    p.add_argument("--data-dir", default=os.environ.get("SM_CHANNEL_TRAIN", "data"))
    p.add_argument("--output-dir", default=os.environ.get("SM_OUTPUT_DATA_DIR", "artifacts"))

    # When no prepared parquet is present, fetch live data instead. Convenient
    # locally, never used inside a SageMaker job.
    p.add_argument("--fetch-if-missing", action="store_true")

    return p.parse_args()


def load_training_frame(data_dir: str, fetch_if_missing: bool) -> pd.DataFrame:
    """Read the prepared training table, or build it from live data locally."""
    path = Path(data_dir)
    parquet_files = sorted(path.glob("*.parquet")) if path.exists() else []

    if parquet_files:
        frame = pd.concat([pd.read_parquet(f) for f in parquet_files]).sort_index()
        print(f"loaded {len(frame)} rows from {len(parquet_files)} file(s) in {path}")
        return frame

    if not fetch_if_missing:
        raise FileNotFoundError(
            f"No parquet files in {path}. Pass --fetch-if-missing to download live data."
        )

    from src.data.fetch import fetch_all
    from src.features.pipeline import make_training_frame

    print("no prepared data found, fetching live market data ...")
    return make_training_frame(fetch_all(period="10y"))


def build_target(frame: pd.DataFrame, target: str) -> np.ndarray:
    """Return or volatility, from the same column. See compare.py."""
    if target == "return":
        return frame["target_return"].to_numpy()
    return frame["target_return"].abs().to_numpy()


def main() -> None:
    from sklearn.ensemble import RandomForestRegressor

    from src.features.pipeline import feature_columns

    args = parse_args()
    print(f"target={args.target}  n_estimators={args.n_estimators}  max_depth={args.max_depth}")

    frame = load_training_frame(args.data_dir, args.fetch_if_missing)
    features = feature_columns(frame)

    # Hold back the most recent rows so evaluation is honest. Without this the
    # model would be scored on data it trained on.
    if args.holdout_days > 0:
        frame_fit = frame.iloc[:-args.holdout_days]
        print(f"holding back the last {args.holdout_days} rows for evaluation")
    else:
        frame_fit = frame
        print("training on all rows (holdout disabled)")

    X = frame_fit[features].to_numpy()
    y = build_target(frame_fit, args.target)

    # Random Forest won the comparison for both targets (see compare.py).
    model = RandomForestRegressor(
        n_estimators=args.n_estimators,
        max_depth=args.max_depth,
        min_samples_leaf=args.min_samples_leaf,
        random_state=args.random_state,
        n_jobs=-1,
    )
    model.fit(X, y)
    print(f"trained on {len(X)} rows, {len(features)} features")

    model_dir = Path(args.model_dir)
    model_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, model_dir / MODEL_FILENAME)

    # The feature order is part of the contract: inference must feed columns in
    # exactly this sequence, or the model silently produces nonsense.
    metadata = {
        "target": args.target,
        "feature_columns": features,
        "n_training_rows": int(len(X)),
        "holdout_days": args.holdout_days,
        "training_window": [str(frame_fit.index[0].date()), str(frame_fit.index[-1].date())],
        "hyperparameters": {
            "n_estimators": args.n_estimators,
            "max_depth": args.max_depth,
            "min_samples_leaf": args.min_samples_leaf,
            "random_state": args.random_state,
        },
    }
    (model_dir / METADATA_FILENAME).write_text(json.dumps(metadata, indent=2))

    print(f"wrote {model_dir / MODEL_FILENAME}")
    print(f"wrote {model_dir / METADATA_FILENAME}")


if __name__ == "__main__":
    main()
