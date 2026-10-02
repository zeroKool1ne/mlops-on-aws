"""The feature pipeline, tested for the two failures that do not announce themselves.

Leakage and train/serve skew both produce a model that looks fine and is
wrong. Neither raises. A metric that improves because the target leaked into a
feature looks exactly like a metric that improved because the model got better,
and the difference is only visible in production, months later.

These are therefore not "does it run" tests. Each one encodes a property the
pipeline claims in its own docstring, so that the claim is checked rather than
trusted.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.features.pipeline import (EXTERNAL_LAG, add_target, align_panel, build_features,
                                   feature_columns, make_inference_row, make_training_frame)


class TestNoLeakage:
    """Rule 1 of the pipeline: features for day t use only information
    available at the end of day t."""

    def test_features_do_not_change_when_the_future_is_removed(self, frames):
        """The decisive test. If a feature row for day t differs depending on
        whether days after t exist in the input, then the future reached
        backwards into it."""
        panel_full = align_panel(frames)
        full = build_features(panel_full).dropna()

        cutoff_position = len(full) - 30
        cutoff = full.index[cutoff_position]

        truncated_frames = {k: v.loc[:cutoff] for k, v in frames.items()}
        truncated = build_features(align_panel(truncated_frames)).dropna()

        pd.testing.assert_series_equal(
            full.loc[cutoff], truncated.loc[cutoff], check_names=False,
        )

    def test_target_is_the_next_day_not_today(self, frames):
        """add_target is the one function allowed to look forward. Verify it
        looks forward by exactly one day - an off-by-one here would make the
        model predict the past, which scores brilliantly and is worthless."""
        panel = align_panel(frames)
        frame = add_target(build_features(panel), panel)

        close = panel["gold_close"]
        expected = close.pct_change().shift(-1)

        aligned = frame["target_return"].dropna()
        pd.testing.assert_series_equal(
            aligned, expected.loc[aligned.index], check_names=False,
        )

    def test_external_markets_are_lagged_further(self, frames):
        """External closes land at a different hour than gold's. The pipeline
        lags them by an extra day rather than reasoning about timezones."""
        panel = align_panel(frames)
        features = build_features(panel)

        expected = panel["vix_close"].pct_change().shift(EXTERNAL_LAG)
        actual = features["vix_ret"].dropna()

        pd.testing.assert_series_equal(
            actual, expected.loc[actual.index], check_names=False,
        )

    def test_gaps_are_forward_filled_never_backfilled(self, frames):
        """Backfilling would move a known future value into a past row."""
        frames = {k: v.copy() for k, v in frames.items()}
        gap_date = frames["dxy"].index[100]
        frames["dxy"] = frames["dxy"].drop(index=gap_date)

        panel = align_panel(frames)
        previous = panel.index[panel.index.get_loc(gap_date) - 1]

        assert panel.loc[gap_date, "dxy_close"] == panel.loc[previous, "dxy_close"]


class TestTrainServeConsistency:
    """ADR-11: training and serving share one pipeline, so the numbers the
    model sees in production are built the way they were in training."""

    def test_inference_row_matches_the_training_row_for_the_same_day(self, frames):
        """The same date, through both paths, must produce the same features.
        A divergence here is train/serve skew by definition."""
        training = make_training_frame(frames)
        features = feature_columns(training)

        as_of = training.index[-10]
        inference = make_inference_row(frames, as_of)

        # check_freq=False: a one-row slice keeps the business-day frequency
        # that dropna() discards. That is an index attribute, not a feature
        # value, and comparing it would test pandas rather than the pipeline.
        pd.testing.assert_frame_equal(
            inference[features], training.loc[[as_of], features], check_freq=False,
        )

    def test_inference_row_never_uses_a_date_after_the_one_asked_for(self, frames):
        as_of = make_training_frame(frames).index[-20]
        assert make_inference_row(frames, as_of).index[-1] <= as_of

    def test_column_order_is_stable(self, frames):
        """Column order is part of the model contract: the estimator is fed a
        numpy array, which carries no names, so a reordering would silently
        feed every feature into the wrong slot."""
        first = feature_columns(make_training_frame(frames))
        second = feature_columns(make_training_frame({k: v.copy() for k, v in frames.items()}))
        assert first == second


class TestShape:
    def test_training_frame_has_no_missing_values(self, training_frame):
        """Rows without a complete feature window are dropped, not imputed."""
        assert not training_frame.isna().to_numpy().any()

    def test_gold_defines_the_calendar(self, frames):
        """A day the gold market is closed is not a day we forecast."""
        assert align_panel(frames).index.equals(frames["gold"].sort_index().index)

    def test_gold_is_mandatory(self, frames):
        del frames["gold"]
        with pytest.raises(ValueError, match="gold"):
            align_panel(frames)

    def test_an_absent_external_market_is_survivable(self, frames):
        """A missing explanatory series degrades the model; it does not
        invalidate the run."""
        del frames["oil"]
        features = feature_columns(make_training_frame(frames))
        assert not any(c.startswith("oil_") for c in features)
        assert any(c.startswith("gold_") for c in features)

    def test_ma_ratio_is_scale_free(self, frames):
        """Expressed as a ratio so it stays comparable across price levels:
        doubling every price must not change it."""
        doubled = {k: v.copy() for k, v in frames.items()}
        doubled["gold"][["open", "high", "low", "close"]] *= 2

        a = build_features(align_panel(frames))["gold_ma_ratio20"].dropna()
        b = build_features(align_panel(doubled))["gold_ma_ratio20"].dropna()

        np.testing.assert_allclose(a.to_numpy(), b.to_numpy(), rtol=1e-10)
