#!/usr/bin/env python3
"""What this project actually costs, measured rather than estimated.

    python scripts/cost-report.py
    python scripts/cost-report.py --json      # for a dashboard or a diff

Why this exists instead of a Cost Explorer query
------------------------------------------------
Development runs in a shared course account, where Cost Explorer reports the
whole cohort's spend. Those numbers are nobody's business here, and they also
answer the wrong question: what this project costs, not what the account
costs. So nothing below asks AWS for a bill. It measures the usage of
resources named `goldmlops-*` and prices it against the published us-east-1
rates - which is also the only method that works before the first invoice
exists.

The Lambda figures are not an approximation. Every invocation writes a REPORT
line carrying its billed duration and configured memory, which is precisely
what AWS charges on, so parsing those lines reconstructs the bill exactly.

Two columns are printed on purpose. `measured` is what the resources that
exist have used so far this month. `projected` is a full month with the daily
schedule running, including the resources the architecture calls for but which
are not deployed yet. A single number would have to be one or the other, and
whichever it was would be wrong somewhere.

Read-only: nothing here creates, modifies or deletes anything.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import date

import boto3

GIB = 1024 ** 3
PROJECT = "goldmlops"
REGION = "us-east-1"

# us-east-1 list prices, checked October 2026. Refresh against
# https://aws.amazon.com/<service>/pricing/ - these move rarely but they do
# move, and a cost model with undated prices cannot be defended.
PRICES_AS_OF = "2026-10"
PRICES = {
    "lambda_gb_second_arm": 0.0000133334,  # arm64 is ~20% under x86
    "lambda_request": 0.20 / 1_000_000,
    "s3_gb_month": 0.023,
    "s3_put_1000": 0.005,
    "ecr_gb_month": 0.10,
    "logs_ingest_gb": 0.50,
    "logs_store_gb_month": 0.03,
    "cw_metric_month": 0.30,
    "cw_alarm_month": 0.10,
    "apigw_million_requests": 1.00,
}

# What a full month looks like once the schedule runs: weekdays only.
TRADING_DAYS = 22


def lambda_costs(session):
    """Exact, from the REPORT line of every invocation this month."""
    logs = session.client("logs")
    first_of_month = int(date.today().replace(day=1).strftime("%s")) * 1000

    functions, total = {}, 0.0
    groups = logs.get_paginator("describe_log_groups").paginate(
        logGroupNamePrefix=f"/aws/lambda/{PROJECT}")

    for page in groups:
        for group in page["logGroups"]:
            name = group["logGroupName"].split("/")[-1]
            gb_seconds, invocations = 0.0, 0

            events = logs.get_paginator("filter_log_events").paginate(
                logGroupName=group["logGroupName"],
                startTime=first_of_month,
                filterPattern="REPORT")

            for page_of_events in events:
                for event in page_of_events["events"]:
                    fields = dict(
                        part.split(": ", 1) for part in event["message"].split("\t")
                        if ": " in part)
                    billed = fields.get("Billed Duration", "").removesuffix(" ms")
                    memory = fields.get("Memory Size", "").removesuffix(" MB")
                    if not (billed and memory):
                        continue
                    gb_seconds += float(billed) / 1000 * float(memory) / 1024
                    invocations += 1

            cost = (gb_seconds * PRICES["lambda_gb_second_arm"]
                    + invocations * PRICES["lambda_request"])
            functions[name] = {
                "invocations": invocations,
                "gb_seconds": round(gb_seconds, 3),
                "cost": cost,
            }
            total += cost

    return total, functions


def ecr_costs(session):
    """Unique layer bytes, not the sum of the image sizes.

    `imageSizeInBytes` counts every layer an image references, so adding it up
    across images multiplies whatever they share - and images built from the
    same source share almost everything. ECR stores each layer once and bills
    it once, so the only honest measurement walks the manifests and collects
    the layer digests into a set.

    On this repository the difference is threefold: 1.046 GiB summed against
    0.349 GiB actually stored.
    """
    ecr = session.client("ecr")
    accepted = [
        "application/vnd.docker.distribution.manifest.v2+json",
        "application/vnd.docker.distribution.manifest.list.v2+json",
        "application/vnd.oci.image.manifest.v1+json",
        "application/vnd.oci.image.index.v1+json",
    ]

    try:
        details = []
        for page in ecr.get_paginator("describe_images").paginate(
                repositoryName=f"{PROJECT}-api"):
            details.extend(page["imageDetails"])
    except ecr.exceptions.RepositoryNotFoundException:
        return 0.0, {"note": "repository does not exist"}

    layers: dict[str, int] = {}
    naive = 0
    pending = [d["imageDigest"] for d in details]
    seen_manifests = set()

    while pending:
        digest = pending.pop()
        if digest in seen_manifests:
            continue
        seen_manifests.add(digest)

        response = ecr.batch_get_image(
            repositoryName=f"{PROJECT}-api",
            imageIds=[{"imageDigest": digest}],
            acceptedMediaTypes=accepted)
        if not response["images"]:
            continue

        manifest = json.loads(response["images"][0]["imageManifest"])
        # An index points at other manifests rather than at layers.
        for child in manifest.get("manifests", []):
            pending.append(child["digest"])
        for layer in manifest.get("layers", []):
            layers[layer["digest"]] = layer["size"]
        if "config" in manifest:
            layers[manifest["config"]["digest"]] = manifest["config"]["size"]

    naive = sum(d["imageSizeInBytes"] for d in details)
    stored = sum(layers.values())

    return stored / GIB * PRICES["ecr_gb_month"], {
        "images": len(details),
        "untagged": sum(1 for d in details if not d.get("imageTags")),
        "unique_layers": len(layers),
        "stored_gib": round(stored / GIB, 4),
        "naive_sum_gib": round(naive / GIB, 4),
    }


def s3_costs(session):
    """Current and noncurrent versions both occupy billable storage."""
    s3 = session.client("s3")
    bucket = None
    for candidate in s3.list_buckets()["Buckets"]:
        if candidate["Name"].startswith(f"{PROJECT}-data"):
            bucket = candidate["Name"]
            break
    if bucket is None:
        return 0.0, {"note": "bucket does not exist"}

    current = noncurrent = 0
    count = 0
    for page in s3.get_paginator("list_object_versions").paginate(Bucket=bucket):
        for version in page.get("Versions", []):
            count += 1
            if version["IsLatest"]:
                current += version["Size"]
            else:
                noncurrent += version["Size"]

    total = current + noncurrent
    return total / GIB * PRICES["s3_gb_month"], {
        "bucket": bucket,
        "versions": count,
        "current_mib": round(current / 1024 ** 2, 2),
        "noncurrent_mib": round(noncurrent / 1024 ** 2, 2),
    }


def logs_costs(session):
    logs = session.client("logs")
    stored = 0
    groups = []
    for page in logs.get_paginator("describe_log_groups").paginate(
            logGroupNamePrefix=f"/aws/lambda/{PROJECT}"):
        for group in page["logGroups"]:
            stored += group.get("storedBytes", 0)
            groups.append({
                "name": group["logGroupName"],
                "stored_bytes": group.get("storedBytes", 0),
                "retention_days": group.get("retentionInDays", "never expires"),
            })

    # Ingestion is charged once per byte, storage every month it stays.
    cost = stored / GIB * (PRICES["logs_ingest_gb"] + PRICES["logs_store_gb_month"])
    return cost, {"groups": groups, "stored_bytes": stored}


def cloudwatch_costs(session):
    """The line item that dominates the finished system and does not exist yet."""
    cw = session.client("cloudwatch")
    alarms = [a["AlarmName"] for page in cw.get_paginator("describe_alarms").paginate()
              for a in page["MetricAlarms"] if a["AlarmName"].startswith(PROJECT)]
    metrics = [m["MetricName"] for page in cw.get_paginator("list_metrics").paginate(
        Namespace="GoldMLOps") for m in page["Metrics"]]

    cost = (len(alarms) * PRICES["cw_alarm_month"]
            + len(set(metrics)) * PRICES["cw_metric_month"])
    return cost, {"alarms": len(alarms), "custom_metrics": len(set(metrics))}


def projection(measured_lambda_detail, ecr_cost):
    """A full month with the schedule running, plus the planned monitoring.

    Lambda is projected from the cheapest observed run rather than the
    average, because the expensive one was a first-ever cold start that
    unpacked the image and timed out its init phase. Using it would overstate
    a steady-state month.
    """
    per_run_gb_seconds = 7.0 * 2048 / 1024  # 7 s billed at 2 GB, measured
    ingest = TRADING_DAYS * per_run_gb_seconds * PRICES["lambda_gb_second_arm"]
    ingest += TRADING_DAYS * PRICES["lambda_request"]

    planned_monitoring = 3 * PRICES["cw_metric_month"] + 4 * PRICES["cw_alarm_month"]

    return {
        "lambda_ingest": ingest,
        "ecr": ecr_cost,
        "s3_after_a_month": TRADING_DAYS * 6 * 115_000 / GIB * PRICES["s3_gb_month"],
        "cloudwatch_planned": planned_monitoring,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    session = boto3.Session(profile_name=args.profile, region_name=REGION)

    lam, lam_detail = lambda_costs(session)
    ecr, ecr_detail = ecr_costs(session)
    s3, s3_detail = s3_costs(session)
    logs, logs_detail = logs_costs(session)
    cw, cw_detail = cloudwatch_costs(session)

    measured = {
        "ECR storage": (ecr, ecr_detail),
        "Lambda": (lam, lam_detail),
        "S3 storage": (s3, s3_detail),
        "CloudWatch logs": (logs, logs_detail),
        "CloudWatch metrics + alarms": (cw, cw_detail),
    }
    total = sum(cost for cost, _ in measured.values())
    proj = projection(lam_detail, ecr)

    if args.json:
        print(json.dumps({
            "prices_as_of": PRICES_AS_OF,
            "region": REGION,
            "measured_total_usd": round(total, 4),
            "measured": {k: round(v[0], 6) for k, v in measured.items()},
            "detail": {k: v[1] for k, v in measured.items()},
            "projected_monthly_usd": round(sum(proj.values()), 4),
            "projected": {k: round(v, 4) for k, v in proj.items()},
        }, indent=2, default=str))
        return

    print(f"\n  Project cost — measured, {REGION}, list prices as of {PRICES_AS_OF}")
    print(f"  Month to date ({date.today().strftime('%B %Y')})\n")
    print(f"  {'Item':<32}{'USD':>10}   detail")
    print(f"  {'-' * 32}{'-' * 10}   {'-' * 34}")
    for name, (cost, detail) in sorted(measured.items(), key=lambda kv: -kv[1][0]):
        note = ", ".join(f"{k}={v}" for k, v in detail.items()
                         if k not in {"groups", "bucket"})
        print(f"  {name:<32}{cost:>10.4f}   {note[:60]}")
    print(f"  {'-' * 32}{'-' * 10}")
    print(f"  {'TOTAL so far this month':<32}{total:>10.4f}\n")

    print(f"  Projected, a full month with the daily schedule and the")
    print(f"  monitoring the architecture calls for:\n")
    for name, cost in sorted(proj.items(), key=lambda kv: -kv[1]):
        print(f"  {name:<32}{cost:>10.4f}")
    print(f"  {'-' * 32}{'-' * 10}")
    print(f"  {'PROJECTED MONTHLY':<32}{sum(proj.values()):>10.4f}\n")

    if ecr and total:
        print(f"  ECR is {ecr / total * 100:.0f}% of the measured cost. The image is")
        print(f"  stored once and billed monthly; the compute is billed per run.\n")


if __name__ == "__main__":
    main()
