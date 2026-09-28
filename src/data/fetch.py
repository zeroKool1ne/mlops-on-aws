"""Market data ingestion.

yfinance is an unofficial scraper of Yahoo Finance: no SLA, no guarantees, and
it breaks without warning when Yahoo changes something. That risk is accepted
deliberately for this project (ADR-8 territory), but it is not ignored: every
download is validated before it is allowed anywhere near the data lake.

A bad download must fail loudly here rather than quietly poison training data.
"""

from __future__ import annotations

import logging

import pandas as pd
import yfinance as yf

log = logging.getLogger(__name__)

# Yahoo tickers behind our internal names. Keeping the mapping here means the
# rest of the codebase never sees a Yahoo-specific symbol.
TICKERS = {
    "gold": "GC=F",        # gold futures - the target instrument
    "dxy": "DX-Y.NYB",     # dollar index - gold is priced in USD
    "oil": "CL=F",         # crude oil - shared inflation driver
    "sp500": "^GSPC",      # equities - risk appetite; gold is the counterweight
    "vix": "^VIX",         # volatility - fear gauge; gold rises on panic
}

REQUIRED_COLUMNS = {"open", "high", "low", "close"}

# Plausibility bounds. Deliberately wide: they catch a broken download
# (zeros, negatives, absurd magnitudes), not an unusual market day.
PRICE_BOUNDS = {
    "gold": (100, 100_000),
    "dxy": (10, 500),
    "oil": (-100, 10_000),   # oil did go negative in April 2020
    "sp500": (100, 100_000),
    "vix": (1, 500),
}


class DataValidationError(Exception):
    """Raised when a download is too broken to be trusted."""


def _normalise(raw: pd.DataFrame) -> pd.DataFrame:
    """Flatten yfinance's column layout and lowercase the names."""
    df = raw.copy()

    # With a single ticker yfinance may still return a MultiIndex.
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df.columns = [str(c).lower().replace(" ", "_") for c in df.columns]
    df.index = pd.to_datetime(df.index).tz_localize(None).normalize()
    df.index.name = "date"
    return df[~df.index.duplicated(keep="last")].sort_index()


def validate(df: pd.DataFrame, name: str, min_rows: int = 30) -> None:
    """Reject a download that cannot be trusted. Raises, never warns silently."""
    if df.empty:
        raise DataValidationError(f"{name}: empty download")

    if len(df) < min_rows:
        raise DataValidationError(f"{name}: only {len(df)} rows, expected at least {min_rows}")

    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise DataValidationError(f"{name}: missing columns {sorted(missing)}")

    if df["close"].isna().all():
        raise DataValidationError(f"{name}: every close is NaN")

    lo, hi = PRICE_BOUNDS.get(name, (-float("inf"), float("inf")))
    closes = df["close"].dropna()
    outside = closes[(closes < lo) | (closes > hi)]
    if not outside.empty:
        raise DataValidationError(
            f"{name}: {len(outside)} closes outside plausible range [{lo}, {hi}], "
            f"e.g. {outside.iloc[0]:.2f} on {outside.index[0].date()}"
        )

    # A long run of identical closes usually means a stale or padded feed.
    if len(closes) > 20 and closes.tail(20).nunique() == 1:
        raise DataValidationError(f"{name}: last 20 closes are all identical - stale feed?")

    nan_share = df["close"].isna().mean()
    if nan_share > 0.1:
        raise DataValidationError(f"{name}: {nan_share:.0%} of closes are NaN")


def fetch_one(name: str, period: str = "10y", interval: str = "1d") -> pd.DataFrame:
    """Download and validate a single instrument."""
    symbol = TICKERS[name]
    log.info("downloading %s (%s)", name, symbol)

    raw = yf.download(symbol, period=period, interval=interval, progress=False, auto_adjust=False)
    df = _normalise(raw)
    validate(df, name)

    log.info("%s: %d rows, %s to %s", name, len(df), df.index[0].date(), df.index[-1].date())
    return df


def fetch_all(period: str = "10y") -> dict[str, pd.DataFrame]:
    """Download every instrument.

    Gold is mandatory - without it there is nothing to predict. An external
    market that fails is logged and skipped, because a missing explanatory
    series degrades the model but does not invalidate the run.
    """
    frames: dict[str, pd.DataFrame] = {}

    for name in TICKERS:
        try:
            frames[name] = fetch_one(name, period=period)
        except Exception as exc:
            if name == "gold":
                raise
            log.warning("skipping %s: %s", name, exc)

    return frames
