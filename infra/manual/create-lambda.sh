#!/usr/bin/env bash
# The ingest function. One image, a different handler from the API.
source "$(dirname "$0")/_env.sh"

aws lambda create-function \
    --function-name "$PROJECT-ingest" \
    --package-type Image \
    --code ImageUri="$IMAGE" \
    --role "arn:aws:iam::$ACCOUNT:role/$PROJECT-lambda-ingest" \
    --architectures arm64 \
    --timeout 300 \
    --memory-size 2048 \
    --environment "Variables={DATA_BUCKET=$BUCKET,LOG_LEVEL=INFO}" \
    --image-config '{"Command":["src.data.ingest.handler"]}'

# The recorded output that used to sit here echoed full ARNs, so it is gone.
# To see the current state:
#     aws lambda get-function-configuration --function-name goldmlops-ingest
