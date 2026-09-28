"""Data drift detection.

A model does not fail, it decays. No exception, no error in the log - the
predictions simply get worse because the world moved away from the data the
model was trained on.

Two measures, deliberately both (see ADR-12 and the PSI/KS deep dive):

    PSI  - a distance measure. Stable across sample sizes, comparable over
           time, and it tells you WHERE in the distribution things moved.
           This is the metric that drives the alert.
    KS   - a hypothesis test. Gives a p-value, needs no binning. Used as a
           cross-check: when both agree, the case is clear.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import ks_2samp

# Industry convention, originally from credit scoring. Not statistically
# derived - calibrate per application rather than treating them as law.
PSI_STABLE = 0.10
PSI_SIGNIFICANT = 0.25

DEFAULT_BINS = 10


def psi(reference: np.ndarray, current: np.ndarray, bins: int = DEFAULT_BINS) -> float:
    """Population Stability Index between two distributions.

    Bin edges always come from the REFERENCE data and are frozen. Recomputing
    them on the current data would put ten percent in every bin again and
    measure nothing.
    """
    reference = np.asarray(reference, dtype=float)
    current = np.asarray(current, dtype=float)
    reference = reference[np.isfinite(reference)]
    current = current[np.isfinite(current)]

    if len(reference) == 0 or len(current) == 0:
        return float("nan")

    edges = np.percentile(reference, np.linspace(0, 100, bins + 1))
    edges = np.unique(edges)                 # collapse ties in flat regions
    if len(edges) < 3:
        return 0.0                           # not enough spread to bin
    edges[0], edges[-1] = -np.inf, np.inf

    ref_pct = np.histogram(reference, bins=edges)[0] / len(reference)
    cur_pct = np.histogram(current, bins=edges)[0] / len(current)

    # Guard against log(0) and division by zero in empty bins.
    ref_pct = np.clip(ref_pct, 1e-6, None)
    cur_pct = np.clip(cur_pct, 1e-6, None)

    return float(np.sum((cur_pct - ref_pct) * np.log(cur_pct / ref_pct)))


def classify(score: float) -> str:
    if not np.isfinite(score):
        return "unknown"
    if score < PSI_STABLE:
        return "stable"
    if score < PSI_SIGNIFICANT:
        return "moderate"
    return "significant"


def compare(reference: pd.DataFrame, current: pd.DataFrame,
            columns: list[str] | None = None) -> pd.DataFrame:
    """Score every feature with both measures.

    Returns one row per feature, sorted by PSI descending, so the worst
    offenders are at the top.
    """
    columns = columns or [c for c in reference.columns if c in current.columns]
    rows = []

    for col in columns:
        ref = reference[col].dropna().to_numpy(dtype=float)
        cur = current[col].dropna().to_numpy(dtype=float)
        if len(ref) < 20 or len(cur) < 20:
            continue

        score = psi(ref, cur)
        ks_stat, p_value = ks_2samp(ref, cur)

        rows.append({
            "feature": col,
            "psi": round(score, 4),
            "verdict": classify(score),
            "ks_stat": round(float(ks_stat), 4),
            "ks_p": round(float(p_value), 4),
            "ks_significant": bool(p_value < 0.05),
        })

    return pd.DataFrame(rows).sort_values("psi", ascending=False).reset_index(drop=True)


def build_reference(frame: pd.DataFrame, columns: list[str],
                    bins: int = DEFAULT_BINS) -> dict:
    """Freeze a reference snapshot for later comparison.

    Stores only the distribution shape - bin edges and shares - never the raw
    data. Written to S3 when a model is promoted, never on every training run
    (ADR-12), otherwise the measurement silently resets itself.
    """
    features = {}
    for col in columns:
        values = frame[col].dropna().to_numpy(dtype=float)
        if len(values) < 20:
            continue
        edges = np.unique(np.percentile(values, np.linspace(0, 100, bins + 1)))
        shares = np.histogram(values, bins=edges)[0] / len(values)
        features[col] = {
            "bin_edges": edges.tolist(),
            "bin_shares": shares.round(6).tolist(),
        }

    return {
        "created_at": pd.Timestamp.utcnow().isoformat(),
        "n_rows": int(len(frame)),
        "window": [str(frame.index[0].date()), str(frame.index[-1].date())],
        "features": features,
    }
