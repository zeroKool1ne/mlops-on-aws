#!/usr/bin/env bash

set -e

aws lambda create-function \
    --function-name goldmlops-ingest \
    --package-type Image \
    --code ImageUri=686699774218.dkr.ecr.us-east-1.amazonaws.com/goldmlops-api:latest \
    --role arn:aws:iam::686699774218:role/goldmlops-lambda-ingest \
    --architectures arm64 \
    --timeout 300 \
    --memory-size 2048 \
    --environment "Variables={DATA_BUCKET=goldmlops-data-686699774218, LOG_LEVEL=INFO}" \
    --image-config '{"Command":["src.data.ingest.handler"]}'


# OUTPUT:

# -east-1:686699774218:function:goldmlops-ingest  goldmlops-ingest        2026-10-02T15:08:51.218+0000    2048     Image   5638a36c-acc9-4aeb-9b03-8aeb010a4fd9    arn:aws:iam::686699774218:role/goldmlops-lambda-ingest   Pending The function is being created.  Creating        300     $LATEST
# ARCHITECTURES   arm64
# VARIABLES       goldmlops-data-686699774218     INFO
# EPHEMERALSTORAGE        512
# COMMAND src.data.ingest.handler
# LOGGINGCONFIG   Text    /aws/lambda/goldmlops-ingest
# SNAPSTART       None    Off
# TRACINGCONFIG   PassThrough
