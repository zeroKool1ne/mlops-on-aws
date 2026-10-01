"""Daily ingestion into the data lake.

Downloads every instrument, validates it (`fetch.py` raises rather than warns),
and writes two things to S3:

    raw/<instrument>/dt=<date>/<instrument>.parquet   one partition per run
    features/latest/training.parquet                  the model-ready table

The raw layer is partitioned by date and never overwritten, so any training run
can be reproduced against the exact data it saw. The feature layer is a single
current file, because training always wants the whole history at once and
assembling it from 2,500 small files on every run would be slower and more
expensive than rewriting one (ADR-3).

Runs as a Lambda on an EventBridge schedule (ADR-4), and as a script locally:

    python -m src.data.ingest --bucket goldmlops-data-123456789012
"""

from __future__ import annotations

import argparse
import io
import logging
import os
from datetime import date

import pandas as pd

log = logging.getLogger(__name__)
logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))

RAW_PREFIX = "raw"
FEATURES_KEY = "features/latest/training.parquet"
DEFAULT_PERIOD = "10y"


def _to_parquet_bytes(frame: pd.DataFrame) -> bytes:
    buffer = io.BytesIO()
    frame.to_parquet(buffer, index=True, compression="snappy")
    return buffer.getvalue()


def _put(bucket: str, key: str, body: bytes) -> str:
    import boto3

    boto3.client("s3").put_object(
        Bucket=bucket, Key=key, Body=body,
        ServerSideEncryption="AES256",
        ContentType="application/octet-stream",
    )
    log.info("wrote s3://%s/%s (%.1f KB)", bucket, key, len(body) / 1024)
    return f"s3://{bucket}/{key}"


def ingest(bucket: str, period: str = DEFAULT_PERIOD, as_of: date | None = None) -> dict:
    """Fetch, validate, write. Returns a summary suitable for a log or an event."""
    from src.data.fetch import fetch_all
    from src.features.pipeline import make_training_frame

    as_of = as_of or date.today()
    frames = fetch_all(period=period)

    written = []
    for name, frame in frames.items():
        key = f"{RAW_PREFIX}/{name}/dt={as_of.isoformat()}/{name}.parquet"
        written.append(_put(bucket, key, _to_parquet_bytes(frame)))

    training = make_training_frame(frames)
    _put(bucket, FEATURES_KEY, _to_parquet_bytes(training))

    summary = {
        "as_of": as_of.isoformat(),
        "instruments": sorted(frames),
        "raw_objects": len(written),
        "training_rows": int(len(training)),
        "training_window": [str(training.index[0].date()), str(training.index[-1].date())],
        "features_key": FEATURES_KEY,
    }
    log.info("ingestion complete: %s", summary)
    return summary


def handler(event, context):  # noqa: ARG001 - Lambda signature
    """EventBridge entry point.

    The bucket comes from the environment, which Terraform sets. Nothing about
    the deployment is hard-coded in the code.
    """
    bucket = os.environ["DATA_BUCKET"]
    period = event.get("period", DEFAULT_PERIOD) if isinstance(event, dict) else DEFAULT_PERIOD
    return {"statusCode": 200, "body": ingest(bucket, period=period)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bucket", default=os.environ.get("DATA_BUCKET"), required=False)
    parser.add_argument("--period", default=DEFAULT_PERIOD)
    args = parser.parse_args()

    if not args.bucket:
        parser.error("pass --bucket or set DATA_BUCKET")

    for key, value in ingest(args.bucket, period=args.period).items():
        print(f"{key:16} {value}")


if __name__ == "__main__":
    main()
