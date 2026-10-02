"""Drift detection, tested for the failure mode that hides itself.

A drift detector that has quietly stopped detecting looks exactly like a
quiet market. The dashboard stays green either way. ADR-12 names the specific
way this happens - recomputing bin edges on the current data instead of
reusing the frozen ones - and the tests below pin that behaviour down, because
it is a one-line change away from silently measuring nothing.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.monitoring.drift import (PSI_SIGNIFICANT, PSI_STABLE, build_reference, classify,
                                  compare_to_reference, psi, psi_from_reference, summarise)

RNG = np.random.default_rng(11)


def normal(n=2000, loc=0.0, scale=1.0):
    return RNG.normal(loc, scale, n)


class TestPSI:
    def test_identical_distributions_score_near_zero(self):
        values = normal()
        assert psi(values, values) < 1e-9

    def test_a_shifted_distribution_is_flagged_significant(self):
        """Two full standard deviations apart is not a subtle change."""
        assert psi(normal(), normal(loc=2.0)) > PSI_SIGNIFICANT

    def test_a_tiny_shift_stays_stable(self):
        assert psi(normal(), normal(loc=0.02)) < PSI_STABLE

    def test_a_widened_distribution_is_detected(self):
        """Drift is not only a change in the mean. Same centre, twice the
        spread, is a different world for a volatility model."""
        assert psi(normal(), normal(scale=2.0)) > PSI_STABLE

    def test_score_is_symmetric_enough_to_be_comparable(self):
        a, b = normal(), normal(loc=1.0)
        assert psi(a, b) == pytest.approx(psi(b, a), rel=0.25)

    def test_too_few_samples_is_not_a_confident_zero(self):
        """Refusing to answer is correct here. Returning 0.0 would read as
        'no drift' when the truth is 'not enough data to tell'."""
        assert np.isnan(psi_from_reference(
            build_reference(pd.DataFrame({"x": normal()}), ["x"])["features"]["x"],
            normal(5),
        ))


class TestFrozenReference:
    """ADR-12: the comparison reuses the reference's bin edges. Recomputing
    them would put ten percent in every bin again and measure nothing."""

    def test_reference_stores_shape_not_raw_data(self):
        reference = build_reference(pd.DataFrame({"x": normal()}), ["x"])
        stored = reference["features"]["x"]
        assert set(stored) == {"bin_edges", "bin_shares"}
        assert sum(stored["bin_shares"]) == pytest.approx(1.0, abs=1e-3)

    def test_scoring_against_its_own_reference_is_near_zero(self):
        values = normal()
        frame = pd.DataFrame({"x": values})
        reference = build_reference(frame, ["x"])
        assert psi_from_reference(reference["features"]["x"], values) < 0.01

    def test_a_shift_against_a_frozen_reference_is_detected(self):
        reference = build_reference(pd.DataFrame({"x": normal()}), ["x"])
        assert psi_from_reference(reference["features"]["x"], normal(loc=2.0)) > PSI_SIGNIFICANT

    def test_values_beyond_the_reference_range_are_not_dropped(self):
        """A feature that has left the old distribution entirely is the
        strongest drift signal there is. Dropping those rows as out of range
        would make the most alarming case the quietest one."""
        reference = build_reference(pd.DataFrame({"x": normal(scale=1.0)}), ["x"])
        far_away = RNG.normal(50.0, 1.0, 500)
        assert psi_from_reference(reference["features"]["x"], far_away) > PSI_SIGNIFICANT


class TestClassify:
    @pytest.mark.parametrize("score,expected", [
        (0.0, "stable"), (0.05, "stable"),
        (0.15, "moderate"), (0.24, "moderate"),
        (0.30, "significant"), (5.0, "significant"),
        (float("nan"), "unknown"),
    ])
    def test_thresholds(self, score, expected):
        assert classify(score) == expected


class TestSummarise:
    def test_the_headline_is_the_worst_feature_not_the_average(self):
        """Drift in one decisive feature is a real problem that an average
        over twenty-nine stable ones would hide completely."""
        scores = pd.DataFrame([
            {"feature": "broken", "psi": 0.90, "verdict": "significant", "n_current": 100},
            *[{"feature": f"fine{i}", "psi": 0.01, "verdict": "stable", "n_current": 100}
              for i in range(29)],
        ])
        summary = summarise(scores)

        assert summary["status"] == "significant"
        assert summary["worst_feature"] == "broken"
        assert summary["max_psi"] == 0.90
        assert summary["mean_psi"] < PSI_STABLE   # the average would say "fine"

    def test_no_comparable_features_is_reported_as_unknown(self):
        assert summarise(pd.DataFrame())["status"] == "unknown"


class TestAgainstRealFeatures:
    """These are the tests that found the monitor was broken before it shipped.

    The reference and the current window come from the same synthetic series,
    so there is no drift to find. Anything above the threshold is the detector
    reporting its own variance as a finding.
    """

    @staticmethod
    def monitored(frame):
        from src.features.pipeline import feature_columns
        from src.monitoring.handler import CALENDAR_FEATURES

        return [f for f in feature_columns(frame) if f not in CALENDAR_FEATURES]

    def test_calendar_features_would_drift_permanently(self, training_frame):
        """Why CALENDAR_FEATURES exists. `month` in any window shorter than a
        year covers part of the year against a reference covering all of it,
        which is not drift - it is the calendar. Left in, this alarm would
        have fired every morning forever."""
        reference = build_reference(training_frame.iloc[:-250], ["month"])
        score = psi_from_reference(
            reference["features"]["month"],
            training_frame["month"].iloc[-60:].to_numpy(dtype=float),
        )
        assert score > 1.0, "expected the calendar artefact this exclusion exists for"

    def test_the_absolute_threshold_alone_would_cry_wolf(self, training_frame):
        """The defect this calibration exists for, pinned down.

        Uncalibrated - no measured noise floor - the same stable series scores
        far above 0.25 against its own history, because a rolling statistic
        compared to a long reference legitimately looks different without
        anything having broken. This test documents that; it is not a wish.
        """
        features = self.monitored(training_frame)
        uncalibrated = build_reference(training_frame.iloc[:-250], features)
        summary = summarise(compare_to_reference(uncalibrated, training_frame.iloc[-250:]))

        assert summary["max_psi"] > PSI_SIGNIFICANT
        assert summary["max_ratio"] is None   # nothing to judge against

    def test_calibrated_against_its_own_noise_floor_it_stays_quiet(self, training_frame):
        """The fix. With the floor measured per feature, stable data is
        reported as stable - which is the only way the one real alarm will
        ever be noticed."""
        from src.monitoring.handler import CURRENT_WINDOW

        features = self.monitored(training_frame)
        reference = build_reference(training_frame.iloc[:-CURRENT_WINDOW], features,
                                    window=CURRENT_WINDOW)
        summary = summarise(compare_to_reference(reference, training_frame.iloc[-CURRENT_WINDOW:]))

        assert summary["status"] in {"stable", "moderate"}, (
            f"{summary['worst_feature']} scored ratio {summary['max_ratio']} "
            f"(psi {summary['max_psi']}, floor {summary['noise_floor']})"
        )
        assert summary["n_significant"] == 0

    def test_every_feature_gets_a_measured_floor(self, training_frame):
        from src.monitoring.handler import CURRENT_WINDOW

        features = self.monitored(training_frame)
        reference = build_reference(training_frame.iloc[:-CURRENT_WINDOW], features,
                                    window=CURRENT_WINDOW)

        assert reference["calibration_window"] == CURRENT_WINDOW
        floors = [f.get("psi_noise_floor") for f in reference["features"].values()]
        assert all(f is not None and f > 0 for f in floors)

    def test_a_genuine_shift_is_still_caught(self, training_frame):
        """Calibration must not have blinded the detector. A feature moved
        four-fold is drift by any definition, and it has to survive the
        noise-floor division."""
        from src.monitoring.handler import CURRENT_WINDOW

        features = self.monitored(training_frame)
        reference = build_reference(training_frame.iloc[:-CURRENT_WINDOW], features,
                                    window=CURRENT_WINDOW)

        shifted = training_frame.iloc[-CURRENT_WINDOW:].copy()
        shifted["gold_vol20"] = shifted["gold_vol20"] * 4 + 0.05

        summary = summarise(compare_to_reference(reference, shifted))
        assert summary["status"] == "significant"
        assert summary["worst_feature"] == "gold_vol20"
