"""Data validation: the gate that must fail loudly.

yfinance is an unofficial scraper with no SLA that breaks without warning when
Yahoo changes something. That risk is accepted (ADR-8 territory) but not
ignored: a bad download has to raise here rather than quietly poison ten years
of training data. Every test below is a shape of breakage that has actually
happened to someone.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.data.fetch import DataValidationError, validate


def good(n: int = 100, price: float = 2000.0) -> pd.DataFrame:
    rng = np.random.default_rng(3)
    close = price * np.exp(np.cumsum(rng.normal(0, 0.01, n)))
    return pd.DataFrame(
        {"open": close, "high": close * 1.01, "low": close * 0.99, "close": close},
        index=pd.bdate_range("2025-01-01", periods=n, name="date"),
    )


def test_a_healthy_download_passes():
    validate(good(), "gold")


class TestRejects:
    def test_an_empty_download(self):
        with pytest.raises(DataValidationError, match="empty"):
            validate(good().iloc[:0], "gold")

    def test_too_few_rows(self):
        """A truncated response is worse than no response: it looks usable."""
        with pytest.raises(DataValidationError, match="only 5 rows"):
            validate(good(5), "gold")

    def test_a_missing_column(self):
        with pytest.raises(DataValidationError, match="missing columns"):
            validate(good().drop(columns=["high"]), "gold")

    def test_all_closes_nan(self):
        frame = good()
        frame["close"] = np.nan
        with pytest.raises(DataValidationError, match="every close is NaN"):
            validate(frame, "gold")

    def test_mostly_nan_closes(self):
        frame = good()
        frame.iloc[:50, frame.columns.get_loc("close")] = np.nan
        with pytest.raises(DataValidationError, match="NaN"):
            validate(frame, "gold")

    def test_an_implausible_price(self):
        """Gold at $7 is not a market event, it is a broken feed."""
        frame = good()
        frame.iloc[10, frame.columns.get_loc("close")] = 7.0
        with pytest.raises(DataValidationError, match="outside plausible range"):
            validate(frame, "gold")

    def test_zeros_instead_of_prices(self):
        frame = good()
        frame["close"] = 0.0
        with pytest.raises(DataValidationError):
            validate(frame, "gold")

    def test_a_stale_feed(self):
        """Twenty identical closes in a row. The request succeeds, the data is
        a week old, and nothing in the response says so."""
        frame = good()
        frame.iloc[-20:, frame.columns.get_loc("close")] = 2000.0
        with pytest.raises(DataValidationError, match="stale"):
            validate(frame, "gold")


class TestBoundsAreWideNotTight:
    """The bounds exist to catch a broken download, not an unusual market day.
    A validator that rejects real history is worse than none, because it fails
    exactly when the market gets interesting."""

    def test_negative_oil_is_accepted(self):
        """April 2020. WTI settled at minus $37 and that was real."""
        frame = good(price=50.0)
        frame.iloc[40, frame.columns.get_loc("close")] = -37.0
        validate(frame, "oil")

    def test_a_vix_panic_spike_is_accepted(self):
        frame = good(price=15.0)
        frame.iloc[60, frame.columns.get_loc("close")] = 82.0
        validate(frame, "vix")

    def test_a_large_single_day_move_is_accepted(self):
        frame = good()
        frame.iloc[70, frame.columns.get_loc("close")] *= 1.08
        validate(frame, "gold")
