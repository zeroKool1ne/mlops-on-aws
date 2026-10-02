"""Experiment tracking and the model registry.

MLflow with a file-based backend store, not a tracking server (ADR-9). A server
needs a host that runs continuously, which costs money and contradicts the
serverless line taken everywhere else in this project — ADR-4 denied even the
daily cron job its own instance. On a solo project nobody else needs to look at
the same runs live, so the main benefit of a server disappears.

What a run records, so that a result can be reproduced rather than merely
believed:

    params        hyperparameters, target, holdout size, feature count
    metrics       RMSE, MAE, the baseline's RMSE, the margin over it
    tags          git commit, data window, library versions, who ran it
    artifacts     the model, its metadata, the evaluation report

The git commit and the library versions are the two that matter most and are
the two most often left out. Without the commit, "RMSE 0.0094" cannot be traced
back to the code that produced it. Without the versions, it cannot be rerun —
the same code against a different scikit-learn is a different experiment.
"""

from __future__ import annotations

import json
import logging
import os
import platform
import subprocess
from contextlib import contextmanager
from pathlib import Path

log = logging.getLogger(__name__)

EXPERIMENT = os.environ.get("MLFLOW_EXPERIMENT", "gold-usd-forecasting")

# File backend by default. Point MLFLOW_TRACKING_URI at a server and the same
# code logs there instead, without an edit.
TRACKING_URI = os.environ.get("MLFLOW_TRACKING_URI", f"file://{Path('mlruns').resolve()}")

REGISTERED_MODEL = os.environ.get("MLFLOW_MODEL_NAME", "gold-volatility")

# A new model has to be better by this much before it is worth promoting.
# Zero would promote on noise: two runs on the same data differ slightly just
# from the random seed, and a registry full of meaningless versions is worse
# than a registry with few.
MIN_IMPROVEMENT_PCT = 2.0


def _git(*args: str) -> str | None:
    try:
        out = subprocess.run(["git", *args], capture_output=True, text=True, timeout=5)
        return out.stdout.strip() or None if out.returncode == 0 else None
    except Exception:
        return None


def environment_tags() -> dict[str, str]:
    """Everything needed to rebuild the conditions this run happened under."""
    import importlib.metadata as md

    def version(package: str) -> str:
        try:
            return md.version(package)
        except Exception:
            return "absent"

    tags = {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "scikit-learn": version("scikit-learn"),
        "pandas": version("pandas"),
        "numpy": version("numpy"),
    }

    commit = _git("rev-parse", "HEAD")
    if commit:
        tags["git_commit"] = commit
        tags["git_branch"] = _git("rev-parse", "--abbrev-ref", "HEAD") or "unknown"
        # A run logged from a dirty tree cannot be reproduced from the commit
        # alone. Recording that is more useful than pretending otherwise.
        tags["git_dirty"] = str(bool(_git("status", "--porcelain")))

    return tags


def available() -> bool:
    """Whether mlflow is importable.

    The container does not install it (see requirements-api.txt), and a
    training run must not fail because tracking is unavailable — losing the
    record is bad, losing the model is worse.
    """
    try:
        import mlflow  # noqa: F401
        return True
    except ImportError:
        return False


@contextmanager
def run(name: str, target: str, nested: bool = False):
    """Open an MLflow run, or do nothing at all if mlflow is absent.

    Yields either the active run or None, so every caller can be written the
    same way regardless of whether tracking is switched on.
    """
    if not available():
        log.warning("mlflow not installed — this run will not be tracked")
        yield None
        return

    import mlflow

    mlflow.set_tracking_uri(TRACKING_URI)
    mlflow.set_experiment(EXPERIMENT)

    with mlflow.start_run(run_name=name, nested=nested) as active:
        mlflow.set_tags({**environment_tags(), "target": target})
        log.info("mlflow run %s (%s)", active.info.run_id, name)
        yield active


def log_params(params: dict) -> None:
    if not available():
        return
    import mlflow
    mlflow.log_params(params)


def log_metrics(metrics: dict, step: int | None = None) -> None:
    """Log only the numbers. NaN and None are skipped rather than coerced:
    directional accuracy is undefined for the volatility target, and a NaN
    logged as 0.0 would read as "always wrong" instead of "not applicable".
    """
    if not available():
        return
    import math

    import mlflow

    clean = {
        k: float(v) for k, v in metrics.items()
        if isinstance(v, (int, float)) and not math.isnan(float(v))
    }
    mlflow.log_metrics(clean, step=step)


def log_artifacts(paths: list[Path | str], subdir: str | None = None) -> None:
    if not available():
        return
    import mlflow

    for path in paths:
        path = Path(path)
        if path.exists():
            mlflow.log_artifact(str(path), artifact_path=subdir)


def log_table(frame, filename: str) -> None:
    """Log a DataFrame as a CSV artifact.

    Comparison results belong in the run, not only in the terminal scrollback
    they were printed to.
    """
    if not available():
        return
    import tempfile

    import mlflow

    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / filename
        frame.to_csv(out, index=True)
        mlflow.log_artifact(str(out))


# --------------------------------------------------------------------------
# registry
# --------------------------------------------------------------------------

def promotion_decision(evaluation: dict) -> tuple[bool, str]:
    """Whether this model should replace the incumbent, and why.

    Two gates, both of which have to pass. Beating the baseline is the floor:
    a model that cannot beat "tomorrow equals today" has learned nothing worth
    deploying (ADR-7). Beating it by a margin is the second gate, so that noise
    between runs does not fill the registry with versions nobody chose.
    """
    if not evaluation.get("beats_baseline", False):
        return False, "does not beat the naive baseline"

    margin = evaluation.get("improvement_over_baseline_pct", 0.0)
    if margin < MIN_IMPROVEMENT_PCT:
        return False, f"beats baseline by only {margin:.2f}% (threshold {MIN_IMPROVEMENT_PCT}%)"

    return True, f"beats baseline by {margin:.2f}%"


def register(model_dir: Path | str, evaluation: dict, run_id: str | None = None) -> dict:
    """Register the model, and promote it only if it earned promotion.

    Every run is registered, including the ones that fail the gate — a rejected
    candidate is evidence, and deleting it would hide that a decision was made.
    Only a model that passes both gates gets the "champion" alias, which is
    what the deployment reads.
    """
    decision = {"registered": False, "promoted": False}

    if not available():
        log.warning("mlflow not installed — model not registered")
        return decision

    import mlflow
    from mlflow.tracking import MlflowClient

    promote, reason = promotion_decision(evaluation)
    decision["reason"] = reason

    model_dir = Path(model_dir)
    mlflow.log_artifacts(str(model_dir), artifact_path="model")

    uri = f"runs:/{run_id or mlflow.active_run().info.run_id}/model"
    version = mlflow.register_model(uri, REGISTERED_MODEL)

    client = MlflowClient()
    client.set_model_version_tag(REGISTERED_MODEL, version.version, "promoted", str(promote))
    client.set_model_version_tag(REGISTERED_MODEL, version.version, "decision", reason)
    client.update_model_version(
        REGISTERED_MODEL, version.version,
        description=f"RMSE {evaluation['model']['rmse']:.6f} against baseline "
                    f"{evaluation['baseline']['rmse']:.6f} — {reason}",
    )

    decision |= {"registered": True, "version": version.version}

    if promote:
        # An alias, not a stage: stages are deprecated in MLflow, and an alias
        # says what the deployment actually reads rather than what phase of a
        # process somebody thinks the model is in.
        client.set_registered_model_alias(REGISTERED_MODEL, "champion", version.version)
        decision["promoted"] = True
        log.info("version %s promoted to champion — %s", version.version, reason)
    else:
        log.info("version %s registered but NOT promoted — %s", version.version, reason)

    return decision


def write_summary(path: Path | str, payload: dict) -> None:
    """Drop the tracking outcome next to the artifacts.

    SageMaker training jobs run on a remote instance and cannot write into a
    local MLflow (ADR-9). This file is how the run's identity travels back with
    the artifact so the metrics can be attached afterwards.
    """
    Path(path).write_text(json.dumps(payload, indent=2))
