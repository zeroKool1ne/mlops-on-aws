#!/usr/bin/env bash
# The API role. Deliberately narrower than the ingest role: this function only
# ever reads the model artifact, so it gets GetObject on models/ and nothing
# else. It does not need the feature table - predict_fn fetches a year of
# market data from Yahoo at request time (see src/models/inference.py).
set -e

ROLE=goldmlops-lambda-api

aws iam get-role --role-name "$ROLE" >/dev/null 2>&1 \
    || aws iam create-role --role-name "$ROLE" \
        --description "Read the model artifact and write its own logs" \
        --assume-role-policy-document file://infra/manual/trust-lambda.json

aws iam put-role-policy --role-name "$ROLE" \
    --policy-name api-permissions \
    --policy-document file://infra/manual/policy-api.json

aws logs describe-log-groups --log-group-name-prefix /aws/lambda/goldmlops-api \
    --query 'logGroups[0]' --output text | grep -q goldmlops-api \
    || aws logs create-log-group --log-group-name /aws/lambda/goldmlops-api
aws logs put-retention-policy --log-group-name /aws/lambda/goldmlops-api --retention-in-days 14

echo "--- Rolle:"
aws iam get-role --role-name "$ROLE" --query 'Role.Arn' --output text
aws iam list-role-policies --role-name "$ROLE" --output text
echo "--- Log-Gruppe:"
aws logs describe-log-groups --log-group-name-prefix /aws/lambda/goldmlops-api \
    --query 'logGroups[].[logGroupName,retentionInDays]' --output text
