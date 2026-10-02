"""The scheduled drift check.

Runs daily after ingestion. Compares the most recent window of features
against the reference frozen when the running model was promoted (ADR-12),
publishes the score to CloudWatch so it can be alarmed and graphed, writes a
full report to S3, and notifies SNS when drift crosses the threshold.

What it deliberately does NOT do is retrain. The decision to spend money on a
training job belongs to an alarm and a human, not to a monitoring function that
runs unattended every morning. The alarm is wired in Terraform; this function
only ever reports.
"""

from __future__ import annotations

import io
import json
import logging
import os
from datetime import date

import pandas as pd

log = logging.getLogger(__name__)
logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))

REFERENCE_KEY = "monitoring/reference/current.json"
FEATURES_KEY = "features/latest/training.parquet"
METRIC_NAMESPACE = "GoldMLOps"

# Features that are deterministic functions of the calendar, not of the market.
# They are EXCLUDED from drift monitoring, and that exclusion is not a
# convenience - it is a correctness fix. Any window shorter than a year covers
# only part of the year, so `month` compared against a multi-year reference
# scores a PSI around 9.0 forever. Left in, this monitor would have raised a
# significant-drift alarm every single morning from the day it was deployed,
# and the one real alarm would have been indistinguishable from the noise.
CALENDAR_FEATURES = frozenset({"month", "day_of_week"})

# How many recent trading days count as "now". One year, not the three months
# this started as.
#
# The reason is effective sample size. Most features here are rolling
# statistics - gold_vol20 is a 20-day standard deviation, so consecutive values
# overlap in 19 of 20 observations and are almost identical. Sixty rows of it
# contain roughly three independent observations, not sixty. PSI assumes
# independent samples, so at a 60-day window it is not measuring drift, it is
# measuring its own variance.
#
# Measured on data known to be stable (the same series, a different window):
#
#     window    max PSI on stable data
#      30 days          4.53
#      60 days          1.55
#     120 days          0.94
#     180 days          0.79
#     250 days          0.13
#
# The 0.25 threshold only separates signal from noise at the bottom of that
# table. See ADR-14.
CURRENT_WINDOW = 250


def _s3():
    import boto3
    return boto3.client("s3")


def load_reference(bucket: str, key: str = REFERENCE_KEY) -> dict | None:
    """The distribution the running model was trained on, or None if unset."""
    try:
        body = _s3().get_object(Bucket=bucket, Key=key)["Body"].read()
        return json.loads(body)
    except Exception as exc:
        log.warning("no drift reference at s3://%s/%s (%s)", bucket, key, exc)
        return None


def load_current(bucket: str, key: str = FEATURES_KEY, window: int = CURRENT_WINDOW) -> pd.DataFrame:
    body = _s3().get_object(Bucket=bucket, Key=key)["Body"].read()
    frame = pd.read_parquet(io.BytesIO(body))
    return frame.tail(window)


def publish_metrics(summary: dict) -> None:
    """Send the score to CloudWatch.

    A number in a log line cannot be alarmed on or graphed. A custom metric
    can, which is what turns this from a script into monitoring.
    """
    import boto3

    if summary.get("max_psi") is None:
        return

    data = [
        {"MetricName": "MaxFeaturePSI", "Value": summary["max_psi"], "Unit": "None"},
        {"MetricName": "MeanFeaturePSI", "Value": summary["mean_psi"], "Unit": "None"},
        {"MetricName": "DriftingFeatures", "Value": summary["n_significant"], "Unit": "Count"},
    ]

    # The alarm is built on the ratio, not the raw PSI. A raw PSI of 7.6 is
    # normal for gold_vol20 and alarming for dxy_ret, so one threshold across
    # both is meaningless (ADR-14). The absolute values stay on the dashboard
    # because they are what makes the ratio auditable.
    if summary.get("max_ratio") is not None:
        data.append({"MetricName": "MaxDriftRatio", "Value": summary["max_ratio"], "Unit": "None"})

    boto3.client("cloudwatch").put_metric_data(Namespace=METRIC_NAMESPACE, MetricData=data)


def notify(topic_arn: str, summary: dict, report_uri: str) -> None:
    import boto3

    boto3.client("sns").publish(
        TopicArn=topic_arn,
        Subject=f"[GoldMLOps] {summary['status']} data drift — "
                f"{summary['worst_feature']} at {summary.get('max_ratio', 0):.1f}x its noise floor",
        Message="\n".join([
            f"Status          {summary['status']}",
            f"Worst feature   {summary['worst_feature']}",
            f"  PSI           {summary['max_psi']:.4f}",
            f"  noise floor   {summary.get('noise_floor')}",
            f"  ratio         {summary.get('max_ratio')}x",
            f"Significant     {summary['n_significant']} of {summary['n_features']} features",
            f"Moderate        {summary['n_moderate']}",
            "",
            f"Full report     {report_uri}",
            "",
            "The ratio is the PSI divided by what this feature scores when nothing",
            "has happened, measured walk-forward on the training data (ADR-14). A",
            "ratio above 3 means this feature has moved more than three times as far",
            "as it normally does. Review the report before retraining: a genuine",
            "market regime change calls for a new model, a broken data feed calls",
            "for a fix.",
        ]),
    )


def check(bucket: str, topic_arn: str | None = None) -> dict:
    """Score today's data against the reference and report."""
    from src.monitoring.drift import compare_to_reference, summarise

    reference = load_reference(bucket)
    if reference is None:
        return {"status": "unknown", "reason": "no reference stored — promote a model first"}

    current = load_current(bucket)
    scores = compare_to_reference(reference, current.drop(columns=list(CALENDAR_FEATURES),
                                                          errors="ignore"))
    summary = summarise(scores)
    summary["reference_window"] = reference["window"]
    summary["checked_at"] = date.today().isoformat()

    report = {"summary": summary, "features": scores.to_dict(orient="records")}
    key = f"monitoring/reports/dt={summary['checked_at']}/drift.json"
    _s3().put_object(
        Bucket=bucket, Key=key,
        Body=json.dumps(report, indent=2).encode(),
        ServerSideEncryption="AES256",
        ContentType="application/json",
    )
    report_uri = f"s3://{bucket}/{key}"

    publish_metrics(summary)
    log.info("drift check: %s", summary)

    if topic_arn and summary["status"] == "significant":
        notify(topic_arn, summary, report_uri)

    summary["report"] = report_uri
    return summary


def handler(event, context):  # noqa: ARG001 - Lambda signature
    return {
        "statusCode": 200,
        "body": check(os.environ["DATA_BUCKET"], os.environ.get("SNS_TOPIC_ARN") or None),
    }


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bucket", default=os.environ.get("DATA_BUCKET"))
    parser.add_argument("--topic-arn", default=os.environ.get("SNS_TOPIC_ARN"))
    args = parser.parse_args()
    if not args.bucket:
        parser.error("pass --bucket or set DATA_BUCKET")

    for key, value in check(args.bucket, args.topic_arn).items():
        print(f"{key:18} {value}")


if __name__ == "__main__":
    main()
