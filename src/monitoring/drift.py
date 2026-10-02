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


# How many times its own noise floor a feature has to move before it counts.
# Not derived either, but it is calibrated per feature rather than borrowed
# whole from another field.
RATIO_MODERATE = 1.5
RATIO_SIGNIFICANT = 3.0


def classify_ratio(ratio: float) -> str:
    """Verdict relative to the feature's measured noise floor (ADR-14)."""
    if not np.isfinite(ratio):
        return "unknown"
    if ratio < RATIO_MODERATE:
        return "stable"
    if ratio < RATIO_SIGNIFICANT:
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


def noise_floor(frame: pd.DataFrame, col: str, window: int,
                bins: int = DEFAULT_BINS, percentile: float = 95.0) -> float:
    """How large a PSI this feature produces when NOTHING has happened.

    This is the number the 0.25 convention is missing. That threshold comes
    from credit scoring, where the monitored quantity is an independent draw
    per customer. Here most features are rolling statistics - gold_vol20 is a
    20-day standard deviation, so consecutive values share 19 of 20
    observations. A one-year window holds on the order of a dozen independent
    observations, not 250, and a slowly wandering process compared against its
    own long history legitimately looks "drifted" without anything breaking.

    Measured **walk-forward**, which matters more than it looks. The obvious
    approach - slide a window through the reference period and score each
    position against the full reference - underestimates the floor, because
    those windows are part of what formed the reference distribution in the
    first place and are therefore unfairly easy. The live window never is: it
    is always the period *after* the reference ends.

    So each sample here is built the way the live comparison is built. A
    reference is fitted on everything before a split point, and the window
    immediately after it is scored against that. The spread of those scores is
    what "nothing has happened, but time has passed" actually costs.

    The windows overlap, so the samples are not independent and the percentile
    is an estimate rather than a confidence bound. It is still a measurement of
    this feature on this data, rather than a constant borrowed from another
    field. See ADR-14.
    """
    values = frame[col].dropna().to_numpy(dtype=float)

    # One reference period plus one scored window, at the very least. Below
    # that there is nothing to walk forward over.
    if len(values) < window * 2:
        return float("nan")

    step = max(window // 4, 1)
    scores: list[float] = []

    for split in range(window, len(values) - window + 1, step):
        past, future = values[:split], values[split:split + window]

        edges = np.unique(np.percentile(past, np.linspace(0, 100, bins + 1)))
        if len(edges) < 3:
            continue

        ref_pct = np.clip(np.histogram(past, bins=edges)[0] / len(past), 1e-6, None)
        clipped = np.clip(future, edges[0], edges[-1])
        cur_pct = np.clip(np.histogram(clipped, bins=edges)[0] / len(clipped), 1e-6, None)
        scores.append(float(np.sum((cur_pct - ref_pct) * np.log(cur_pct / ref_pct))))

    return float(np.percentile(scores, percentile)) if scores else float("nan")


def build_reference(frame: pd.DataFrame, columns: list[str],
                    bins: int = DEFAULT_BINS, window: int | None = None) -> dict:
    """Freeze a reference snapshot for later comparison.

    Stores only the distribution shape - bin edges and shares - never the raw
    data. Written to S3 when a model is promoted, never on every training run
    (ADR-12), otherwise the measurement silently resets itself.

    Each feature also carries its own measured noise floor (see `noise_floor`
    and ADR-14), so that the live comparison can ask "is this more than this
    feature normally does" rather than "is this above 0.25".
    """
    features = {}
    for col in columns:
        values = frame[col].dropna().to_numpy(dtype=float)
        if len(values) < 20:
            continue
        edges = np.unique(np.percentile(values, np.linspace(0, 100, bins + 1)))
        shares = np.histogram(values, bins=edges)[0] / len(values)
        entry = {
            "bin_edges": edges.tolist(),
            "bin_shares": shares.round(6).tolist(),
        }
        if window:
            floor = noise_floor(frame, col, window, bins)
            if np.isfinite(floor):
                entry["psi_noise_floor"] = round(floor, 4)
        features[col] = entry

    return {
        # Timestamp.utcnow() is deprecated in pandas 4.
        "created_at": pd.Timestamp.now("UTC").isoformat(),
        "n_rows": int(len(frame)),
        "window": _index_window(frame),
        "calibration_window": window,
        "features": features,
    }


def _index_window(frame: pd.DataFrame) -> list[str]:
    """First and last index label, as dates when the index carries dates.

    The production frame is always indexed by trading day, but this function
    has no business crashing on a frame that is not - a reference built from a
    plain integer index is still a valid reference, and losing the whole
    snapshot over a label format would be the wrong trade.
    """
    if len(frame) == 0:
        return []
    first, last = frame.index[0], frame.index[-1]
    if isinstance(frame.index, pd.DatetimeIndex):
        return [str(first.date()), str(last.date())]
    return [str(first), str(last)]


def psi_from_reference(stored: dict, current: np.ndarray) -> float:
    """PSI against a frozen reference, using its stored bin edges.

    `build_reference` deliberately keeps only the distribution shape, not the
    raw data. That makes the reference small and privacy-free, but it means the
    comparison cannot recompute bin edges - it has to reuse the frozen ones,
    which is exactly what ADR-12 requires.
    """
    edges = np.asarray(stored["bin_edges"], dtype=float)
    ref_pct = np.clip(np.asarray(stored["bin_shares"], dtype=float), 1e-6, None)

    current = np.asarray(current, dtype=float)
    current = current[np.isfinite(current)]
    if len(current) < 20:
        return float("nan")

    # Values beyond the reference range belong in the outermost bins, not
    # nowhere: a feature that has moved off the edge of the old distribution is
    # the strongest drift signal there is and must not be silently dropped.
    clipped = np.clip(current, edges[0], edges[-1])
    cur_pct = np.clip(np.histogram(clipped, bins=edges)[0] / len(clipped), 1e-6, None)

    return float(np.sum((cur_pct - ref_pct) * np.log(cur_pct / ref_pct)))


def compare_to_reference(reference: dict, current: pd.DataFrame) -> pd.DataFrame:
    """Score the current window against a stored reference, feature by feature.

    Returns one row per feature, worst first. This is the function the
    scheduled drift check calls; `compare` is its two-frame sibling for
    interactive analysis in a notebook.
    """
    rows = []
    for col, stored in reference["features"].items():
        if col not in current.columns:
            continue
        values = current[col].dropna().to_numpy(dtype=float)
        score = psi_from_reference(stored, values)
        floor = stored.get("psi_noise_floor")

        # Judge against the feature's own measured floor where one exists, and
        # fall back to the absolute convention where it does not. The raw PSI
        # is reported either way, so the judgement can always be re-derived.
        if floor and np.isfinite(score):
            ratio = score / max(floor, 1e-6)
            verdict = classify_ratio(ratio)
        else:
            ratio, verdict = None, classify(score)

        rows.append({
            "feature": col,
            "psi": round(score, 4) if np.isfinite(score) else None,
            "noise_floor": floor,
            "ratio": round(ratio, 3) if ratio is not None else None,
            "verdict": verdict,
            "n_current": int(len(values)),
        })

    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    has_ratio = "ratio" in frame.columns and frame["ratio"].notna().any()
    return frame.sort_values("ratio" if has_ratio else "psi",
                             ascending=False, na_position="last").reset_index(drop=True)


def summarise(scores: pd.DataFrame) -> dict:
    """Condense per-feature scores into the few numbers an alert needs.

    The headline is the MAXIMUM PSI, not the mean. Drift in one decisive
    feature is a real problem that an average over twenty-nine stable features
    would hide completely.
    """
    if scores.empty:
        return {"status": "unknown", "reason": "no comparable features"}

    usable = scores.dropna(subset=["psi"])
    if usable.empty:
        return {"status": "unknown", "reason": "no feature produced a usable score"}

    counts = usable["verdict"].value_counts().to_dict()

    # Rank by ratio where it exists, because that is what the verdict is based
    # on. Sorting by raw PSI would put the noisiest feature on top rather than
    # the one that has moved most relative to its own normal behaviour.
    has_ratio = "ratio" in usable.columns and usable["ratio"].notna().any()
    ranked = usable.sort_values("ratio" if has_ratio else "psi",
                                ascending=False, na_position="last")
    worst = ranked.iloc[0]

    return {
        "status": str(worst["verdict"]),
        "max_psi": float(worst["psi"]),
        "max_ratio": float(worst["ratio"]) if pd.notna(worst.get("ratio")) else None,
        "noise_floor": float(worst["noise_floor"]) if pd.notna(worst.get("noise_floor")) else None,
        "worst_feature": str(worst["feature"]),
        "mean_psi": round(float(usable["psi"].mean()), 4),
        "n_features": int(len(usable)),
        "n_significant": int(counts.get("significant", 0)),
        "n_moderate": int(counts.get("moderate", 0)),
        "n_stable": int(counts.get("stable", 0)),
    }
