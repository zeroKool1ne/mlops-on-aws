"""The promotion gate.

This is the only place in the project where an automated decision replaces
what is served to callers, so it is the place where being wrong is most
expensive. Two gates have to pass: beating the naive baseline at all (ADR-7),
and beating it by enough that the margin is not noise between random seeds.
"""

from __future__ import annotations

import pytest

from src.models.tracking import MIN_IMPROVEMENT_PCT, promotion_decision


def evaluation(beats: bool, margin: float) -> dict:
    return {"beats_baseline": beats, "improvement_over_baseline_pct": margin}


class TestGate:
    def test_a_clear_improvement_is_promoted(self):
        promote, reason = promotion_decision(evaluation(True, 8.03))
        assert promote
        assert "8.03" in reason

    def test_failing_to_beat_the_baseline_is_rejected(self):
        """The floor. A model that cannot beat 'tomorrow equals today' has
        learned nothing worth deploying, however good its RMSE looks."""
        promote, reason = promotion_decision(evaluation(False, -0.80))
        assert not promote
        assert "baseline" in reason

    def test_beating_the_baseline_by_too_little_is_rejected(self):
        """Two runs on the same data differ slightly from the seed alone. A
        gate at zero would promote on noise and fill the registry with
        versions nobody chose."""
        promote, reason = promotion_decision(evaluation(True, 0.5))
        assert not promote
        assert "threshold" in reason

    def test_exactly_at_the_threshold_is_promoted(self):
        promote, _ = promotion_decision(evaluation(True, MIN_IMPROVEMENT_PCT))
        assert promote

    def test_just_below_the_threshold_is_not(self):
        promote, _ = promotion_decision(evaluation(True, MIN_IMPROVEMENT_PCT - 0.01))
        assert not promote

    def test_a_missing_verdict_is_treated_as_failure(self):
        """An evaluation that never ran must not promote by default. Absence
        of a rejection is not an approval."""
        promote, _ = promotion_decision({})
        assert not promote

    def test_the_reason_is_always_stated(self):
        for ev in [evaluation(True, 9.0), evaluation(False, -1.0), evaluation(True, 0.1), {}]:
            _, reason = promotion_decision(ev)
            assert reason and isinstance(reason, str)
