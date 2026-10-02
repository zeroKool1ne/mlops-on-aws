aws iam put-role-policy \
  --role-name goldmlops-lambda-ingest \
  --policy-name ingest-permissions \
  --policy-document file://infra/manual/policy-ingest.json