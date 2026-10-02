"""Model interpretability: what the model actually uses, and how.

Three measures, because each one answers a different question and each one
alone is misleading:

    impurity importance   What the tree used to split on. Free, and biased
                          towards high-cardinality features - it will rank a
                          continuous feature above a binary one that matters
                          more. Reported for comparison, never on its own.
    permutation importance  How much worse the model gets when one feature is
                          shuffled. Measured on held-out data, so it answers
                          "does this feature help it predict" rather than
                          "did the tree like splitting on it".
    SHAP                  Per-prediction attribution. The only one that can
                          explain a single forecast rather than the model in
                          aggregate, and the only one with a direction.

For a volatility model the direction matters: knowing that a high VIX pushes
the forecast up is a statement a person can check against how markets work.
"Feature ranked third" is not.

    python -m src.models.explain --model-dir artifacts --fetch-if-missing
"""

from __future__ import annotations

import argparse
import json
import logging
import os
from pathlib import Path

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)
logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))

# Held-out rows used for the explanation. SHAP on a tree ensemble is exact but
# scales with rows times trees, and 126 days is already enough for a stable
# mean attribution.
EXPLAIN_ROWS = 126
TOP_N = 15


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--model-dir", default="artifacts")
    p.add_argument("--data-dir", default="data")
    p.add_argument("--output-dir", default="artifacts/explain")
    p.add_argument("--rows", type=int, default=EXPLAIN_ROWS)
    p.add_argument("--fetch-if-missing", action="store_true")
    return p.parse_args()


def load(model_dir: str):
    import joblib

    from src.models.train import METADATA_FILENAME, MODEL_FILENAME

    path = Path(model_dir)
    model = joblib.load(path / MODEL_FILENAME)
    metadata = json.loads((path / METADATA_FILENAME).read_text())
    return model, metadata


def impurity_importance(model, features: list[str]) -> pd.Series:
    if not hasattr(model, "feature_importances_"):
        return pd.Series(dtype=float)
    return pd.Series(model.feature_importances_, index=features, name="impurity")


def permutation_importance_scores(model, X: pd.DataFrame, y: np.ndarray,
                                  features: list[str], seed: int = 42) -> pd.Series:
    """How much RMSE degrades when each feature is shuffled.

    Ten repeats, because a single shuffle of a 126-row sample is noisy enough
    to reorder the middle of the ranking between runs.
    """
    from sklearn.inspection import permutation_importance

    result = permutation_importance(
        model, X, y, n_repeats=10, random_state=seed,
        scoring="neg_root_mean_squared_error", n_jobs=-1,
    )
    return pd.Series(result.importances_mean, index=features, name="permutation")


def shap_values(model, X: pd.DataFrame):
    """Exact SHAP values via the tree explainer.

    TreeExplainer is exact for tree ensembles, not an approximation, and it
    does not need a background dataset. For a non-tree model this would have to
    fall back to KernelExplainer, which is sampled and far slower.
    """
    import shap

    explainer = shap.TreeExplainer(model)
    return explainer(X)


def directional_effect(shap_result, X: pd.DataFrame) -> pd.Series:
    """Sign of each feature's effect: does a high value push the forecast up?

    The correlation between a feature's value and its own SHAP contribution.
    Near +1 means "more of this raises the prediction", near -1 the reverse,
    near 0 means the effect is non-monotonic - which is itself worth knowing,
    because it is the case a linear model would have missed entirely.
    """
    values = shap_result.values
    out = {}
    for i, col in enumerate(X.columns):
        feature, contribution = X[col].to_numpy(dtype=float), values[:, i]
        if np.std(feature) == 0 or np.std(contribution) == 0:
            out[col] = np.nan
        else:
            out[col] = float(np.corrcoef(feature, contribution)[0, 1])
    return pd.Series(out, name="direction")


def plot(shap_result, X: pd.DataFrame, out_dir: Path, target: str) -> list[Path]:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import shap

    written = []

    # Beeswarm: every point is one day's attribution. Shows spread and
    # direction at once, which a bar chart of means cannot.
    plt.figure()
    shap.summary_plot(shap_result, X, max_display=TOP_N, show=False)
    plt.title(f"SHAP attribution per prediction — target: {target}", fontsize=11)
    plt.tight_layout()
    path = out_dir / "shap_beeswarm.png"
    plt.savefig(path, dpi=150, bbox_inches="tight")
    plt.close()
    written.append(path)

    plt.figure()
    shap.summary_plot(shap_result, X, plot_type="bar", max_display=TOP_N, show=False)
    plt.title(f"Mean absolute SHAP value — target: {target}", fontsize=11)
    plt.tight_layout()
    path = out_dir / "shap_importance.png"
    plt.savefig(path, dpi=150, bbox_inches="tight")
    plt.close()
    written.append(path)

    return written


def main() -> None:
    from src.models import tracking
    from src.models.train import build_target, load_training_frame

    args = parse_args()
    model, metadata = load(args.model_dir)
    target, features = metadata["target"], metadata["feature_columns"]

    frame = load_training_frame(args.data_dir, args.fetch_if_missing)
    holdout = frame.iloc[-args.rows:]
    X = holdout[features]
    y = build_target(holdout, target)
    log.info("explaining %d held-out rows, %d features, target=%s", len(X), len(features), target)

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    result = shap_values(model, X)
    mean_abs = pd.Series(np.abs(result.values).mean(axis=0), index=features, name="shap_mean_abs")

    table = pd.concat([
        mean_abs,
        directional_effect(result, X),
        permutation_importance_scores(model, X, y, features),
        impurity_importance(model, features),
    ], axis=1).sort_values("shap_mean_abs", ascending=False)

    # Rank by each measure, so disagreement between them is visible rather
    # than hidden behind one chosen ordering.
    for col in ("shap_mean_abs", "permutation", "impurity"):
        if col in table and table[col].notna().any():
            table[f"rank_{col}"] = table[col].rank(ascending=False).astype("Int64")

    csv_path = out_dir / "feature_importance.csv"
    table.to_csv(csv_path)

    images = plot(result, X, out_dir, target)

    print(f"\nTop {TOP_N} features by mean |SHAP| — target: {target}")
    print("-" * 78)
    shown = table.head(TOP_N)[["shap_mean_abs", "direction", "permutation", "rank_impurity"]]
    print(shown.to_string(float_format=lambda v: f"{v:9.5f}"))
    print("\ndirection: +1 a high value raises the forecast, -1 lowers it, ~0 non-monotonic")

    with tracking.run(f"explain-{target}", target=target):
        tracking.log_params({"explain_rows": len(X), "top_n": TOP_N})
        tracking.log_table(table, "feature_importance.csv")
        tracking.log_artifacts(images, subdir="explain")
        # The top feature's share of total attribution: a model leaning on one
        # feature is fragile in a way an importance ranking does not show.
        tracking.log_metrics({
            "top_feature_share": float(mean_abs.max() / mean_abs.sum()),
            "top5_share": float(mean_abs.nlargest(5).sum() / mean_abs.sum()),
        })

    print(f"\nwrote {csv_path}")
    for path in images:
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
