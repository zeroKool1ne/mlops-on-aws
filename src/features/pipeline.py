"""Feature engineering - shared by training and serving.

This module is the single source of truth for how raw market data becomes
model input. Training imports it, the prediction service imports it. Any
divergence between the two would be train/serve skew, which is invisible
until the model quietly degrades in production (see ADR-11).

Design rules enforced here:
  1. Features for day t use only information available at the end of day t.
  2. Gaps are forward-filled only. Backfilling would move future values into
     the past, which is leakage.
  3. External markets are lagged by EXTERNAL_LAG days on top of that, because
     trading calendars and closing times differ between gold futures, equities
     and oil. One extra day costs a little signal and removes the whole class
     of "did that close happen before or after ours" questions.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# Gold is the target instrument; the rest are explanatory markets.
GOLD = "gold"
EXTERNALS = ["dxy", "oil", "sp500", "vix"]

# Conservative safety margin against differing closing times (see module docstring).
EXTERNAL_LAG = 1

# Windows used for lag and rolling features, in trading days.
LAGS = [1, 2, 3, 5, 10]
WINDOWS = [5, 10, 20]


def _returns(close: pd.Series) -> pd.Series:
    """Simple daily return. Stationary, unlike the price level (ADR-10)."""
    return close.pct_change()


def align_panel(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Join per-ticker OHLCV frames onto the gold trading calendar.

    Gold defines the index because it is what we predict; a day the gold market
    is closed is not a day we forecast. Other markets are reindexed onto it and
    forward-filled, never backfilled.
    """
    if GOLD not in frames:
        raise ValueError(f"'{GOLD}' is required, got: {sorted(frames)}")

    gold = frames[GOLD].sort_index()
    panel = pd.DataFrame(index=gold.index)

    panel["gold_close"] = gold["close"]
    panel["gold_high"] = gold["high"]
    panel["gold_low"] = gold["low"]
    panel["gold_volume"] = gold.get("volume", np.nan)

    for name in EXTERNALS:
        if name not in frames:
            continue
        series = frames[name].sort_index()["close"]
        # reindex onto the gold calendar, then forward-fill only
        panel[f"{name}_close"] = series.reindex(panel.index).ffill()

    return panel


def build_features(panel: pd.DataFrame) -> pd.DataFrame:
    """Turn an aligned price panel into model features.

    Returns a frame indexed by date. Every column is known at the close of that
    date. The target is added separately by `add_target`, which is the only
    place that looks into the future.
    """
    out = pd.DataFrame(index=panel.index)

    gold_ret = _returns(panel["gold_close"])

    # --- gold's own recent behaviour -------------------------------------
    for lag in LAGS:
        out[f"gold_ret_lag{lag}"] = gold_ret.shift(lag - 1)

    for window in WINDOWS:
        out[f"gold_ret_mean{window}"] = gold_ret.rolling(window).mean()
        out[f"gold_vol{window}"] = gold_ret.rolling(window).std()

    # Distance from a moving average: a classic mean-reversion signal,
    # expressed as a ratio so it stays comparable across price levels.
    for window in WINDOWS:
        ma = panel["gold_close"].rolling(window).mean()
        out[f"gold_ma_ratio{window}"] = panel["gold_close"] / ma - 1

    # Intraday range as a volatility proxy that does not need a window.
    out["gold_range"] = (panel["gold_high"] - panel["gold_low"]) / panel["gold_close"]

    # --- external markets, additionally lagged ---------------------------
    for name in EXTERNALS:
        col = f"{name}_close"
        if col not in panel:
            continue
        ext_ret = _returns(panel[col]).shift(EXTERNAL_LAG)
        out[f"{name}_ret"] = ext_ret
        out[f"{name}_ret_mean5"] = ext_ret.rolling(5).mean()
        out[f"{name}_vol10"] = ext_ret.rolling(10).std()

    # --- calendar --------------------------------------------------------
    out["day_of_week"] = panel.index.dayofweek
    out["month"] = panel.index.month

    return out


def add_target(features: pd.DataFrame, panel: pd.DataFrame) -> pd.DataFrame:
    """Attach the prediction target: the NEXT day's gold return (ADR-10).

    This is the only function that shifts backwards in time. Keeping it
    separate makes the leakage boundary explicit and reviewable.
    """
    gold_ret = _returns(panel["gold_close"])
    out = features.copy()
    out["target_return"] = gold_ret.shift(-1)
    return out


def feature_columns(frame: pd.DataFrame) -> list[str]:
    """Every column except the target. Order is fixed by construction."""
    return [c for c in frame.columns if not c.startswith("target_")]


def make_training_frame(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Full path from raw OHLCV frames to a model-ready training table."""
    panel = align_panel(frames)
    features = build_features(panel)
    frame = add_target(features, panel)
    # Rows without a complete feature window or without a target are unusable.
    return frame.dropna()


def make_inference_row(frames: dict[str, pd.DataFrame], as_of: str | pd.Timestamp) -> pd.DataFrame:
    """Build the single feature row used to predict the day after `as_of`.

    Same functions, same order, same parameters as training - that identity is
    the entire point of this module.
    """
    panel = align_panel(frames)
    features = build_features(panel).dropna()

    as_of = pd.Timestamp(as_of)
    usable = features.loc[features.index <= as_of]
    if usable.empty:
        raise ValueError(f"No complete feature row available on or before {as_of.date()}")

    return usable.iloc[[-1]]
