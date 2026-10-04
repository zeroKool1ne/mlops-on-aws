#!/usr/bin/env bash
# The API function: the same image as the ingest function, a different handler.
#
# Timeout is 60 s although API Gateway gives up at 30. That is deliberate: on a
# cold start the function downloads the model from S3 and a year of market data
# from Yahoo, which can exceed 30 s. API Gateway returns 504, but the function
# finishes and the container stays warm - so the next request is fast. Cutting
# the function off at 29 s would throw that warm container away.
set -e

FN=goldmlops-api
IMAGE=686699774218.dkr.ecr.us-east-1.amazonaws.com/goldmlops-api:latest
ROLE=arn:aws:iam::686699774218:role/goldmlops-lambda-api
BUCKET=goldmlops-data-686699774218

if aws lambda get-function --function-name "$FN" >/dev/null 2>&1; then
    echo "--- existiert, aktualisiere Code und Konfiguration"
    aws lambda update-function-code --function-name "$FN" --image-uri "$IMAGE" >/dev/null
    aws lambda wait function-updated --function-name "$FN"
    aws lambda update-function-configuration --function-name "$FN" \
        --memory-size 2048 --timeout 60 >/dev/null
else
    aws lambda create-function \
        --function-name "$FN" \
        --package-type Image \
        --code ImageUri="$IMAGE" \
        --role "$ROLE" \
        --architectures arm64 \
        --memory-size 2048 \
        --timeout 60 \
        --image-config '{"Command":["src.api.handler.handler"]}' \
        --environment "$(cat <<JSON
{"Variables":{
  "MODEL_S3_URI":"s3://$BUCKET/models/current/model.tar.gz",
  "DATA_BUCKET":"$BUCKET",
  "LOG_LEVEL":"INFO",
  "SAGEMAKER_ENDPOINT":""
}}
JSON
)" \
        >/dev/null
fi

aws lambda wait function-active-v2 --function-name "$FN"
echo "--- Funktion:"
aws lambda get-function-configuration --function-name "$FN" \
    --query '[FunctionName,State,Architectures[0],MemorySize,Timeout,ImageConfigResponse.ImageConfig.Command[0]]' --output text
