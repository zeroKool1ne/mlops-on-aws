"""Where the model actually runs.

Two backends behind one function. Which one is used depends on a single
environment variable, not on a code change:

    SAGEMAKER_ENDPOINT set    -> the request is forwarded to the SageMaker
                                 Serverless endpoint (ADR-1, ADR-2). This is
                                 production.
    SAGEMAKER_ENDPOINT unset  -> the model is loaded into this process from
                                 MODEL_DIR or from S3. This is local
                                 development and the fallback path.

The fallback is not a shortcut. It is what makes the service demonstrable on a
laptop with no AWS account, and it is the same prediction code either way -
`src.models.inference` is imported by both the SageMaker container and by this
module, so there is one implementation, not two.
"""

from __future__ import annotations

import json
import logging
import os
import tarfile
import tempfile
from pathlib import Path

log = logging.getLogger(__name__)

ENDPOINT_NAME = os.environ.get("SAGEMAKER_ENDPOINT", "").strip()
MODEL_DIR = os.environ.get("MODEL_DIR", "artifacts")
MODEL_S3_URI = os.environ.get("MODEL_S3_URI", "").strip()

# Lambda gives us /tmp and nothing else writable.
LOCAL_CACHE = Path(os.environ.get("MODEL_CACHE_DIR", tempfile.gettempdir())) / "model"

_bundle: dict | None = None


def serving_mode() -> str:
    return "sagemaker" if ENDPOINT_NAME else "local"


# --------------------------------------------------------------------------
# local backend
# --------------------------------------------------------------------------

def _download_artifact() -> Path:
    """Fetch and unpack model.tar.gz from S3 into the local cache.

    Called once per container start, never per request. A Lambda that has
    already warmed up answers from memory.
    """
    import boto3

    bucket, _, key = MODEL_S3_URI.removeprefix("s3://").partition("/")
    LOCAL_CACHE.mkdir(parents=True, exist_ok=True)
    archive = LOCAL_CACHE / "model.tar.gz"

    log.info("downloading model artifact from %s", MODEL_S3_URI)
    boto3.client("s3").download_file(bucket, key, str(archive))

    with tarfile.open(archive) as tar:
        tar.extractall(LOCAL_CACHE, filter="data")
    archive.unlink(missing_ok=True)
    return LOCAL_CACHE


def load_bundle() -> dict:
    """Load model and metadata once, and keep them for the process lifetime."""
    global _bundle
    if _bundle is not None:
        return _bundle

    from src.models.inference import model_fn

    candidate = Path(MODEL_DIR)
    if not (candidate / "model.joblib").exists() and MODEL_S3_URI:
        candidate = _download_artifact()

    _bundle = model_fn(str(candidate))
    log.info("model loaded from %s (target=%s)", candidate, _bundle["metadata"]["target"])
    return _bundle


def metadata() -> dict | None:
    """Model metadata, or None when no artifact is reachable."""
    try:
        return load_bundle()["metadata"]
    except Exception as exc:
        log.warning("model metadata unavailable: %s", exc)
        return None


def _predict_local(payload: dict) -> dict:
    from src.models.inference import input_fn, predict_fn

    bundle = load_bundle()
    return predict_fn(input_fn(json.dumps(payload)), bundle)


# --------------------------------------------------------------------------
# sagemaker backend
# --------------------------------------------------------------------------

def _predict_sagemaker(payload: dict) -> dict:
    import boto3

    response = boto3.client("sagemaker-runtime").invoke_endpoint(
        EndpointName=ENDPOINT_NAME,
        ContentType="application/json",
        Accept="application/json",
        Body=json.dumps(payload),
    )
    return json.loads(response["Body"].read())


# --------------------------------------------------------------------------
# the one entry point the API calls
# --------------------------------------------------------------------------

def predict(payload: dict) -> dict:
    """Produce a prediction using whichever backend is configured."""
    if ENDPOINT_NAME:
        return _predict_sagemaker(payload)
    return _predict_local(payload)
