aws lambda invoke \
    --function-name goldmlops-ingest \
    --cli-binary-format raw-in-base64-out \
    --payload '{}' \
    response.json