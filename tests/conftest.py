"""Synthetic market data.

The tests must not download anything. yfinance is an unofficial scraper with
no SLA (see src/data/fetch.py), so a test suite that depends on it fails for
reasons that have nothing to do with the code under test.

The fixtures below are deliberately deterministic: a fixed seed and a fixed
calendar, so a failure means a real regression rather than an unlucky draw.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

SEED = 7

# Six years of business days. Not an arbitrary round number: the drift monitor
# compares a one-year window against a reference, and a fixture short enough to
# leave only a few hundred rows in the reference makes the reference itself the
# unstable thing. The real series is about 2,500 trading days, so this is the
# same order of magnitude.
N_DAYS = 1600


def _ohlcv(start_price: float, volatility: float, seed: int, n: int = N_DAYS) -> pd.DataFrame:
    """A plausible random walk with the columns fetch.py produces."""
    rng = np.random.default_rng(seed)
    index = pd.bdate_range("2024-01-01", periods=n, name="date")

    returns = rng.normal(0, volatility, n)
    close = start_price * np.exp(np.cumsum(returns))
    spread = np.abs(rng.normal(0, volatility, n)) * close

    return pd.DataFrame(
        {
            "open": close * (1 + rng.normal(0, volatility / 2, n)),
            "high": close + spread,
            "low": close - spread,
            "close": close,
            "volume": rng.integers(1_000, 100_000, n),
        },
        index=index,
    )


@pytest.fixture
def frames() -> dict[str, pd.DataFrame]:
    """One frame per instrument, as fetch_all returns."""
    return {
        "gold": _ohlcv(2000.0, 0.009, SEED),
        "dxy": _ohlcv(100.0, 0.004, SEED + 1),
        "oil": _ohlcv(75.0, 0.018, SEED + 2),
        "sp500": _ohlcv(4500.0, 0.010, SEED + 3),
        "vix": _ohlcv(15.0, 0.060, SEED + 4),
    }


@pytest.fixture
def training_frame(frames):
    from src.features.pipeline import make_training_frame

    return make_training_frame(frames)
