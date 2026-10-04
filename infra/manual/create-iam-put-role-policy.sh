#!/usr/bin/env bash
source "$(dirname "$0")/_env.sh"

aws iam put-role-policy \
  --role-name $PROJECT-lambda-ingest \
  --policy-name ingest-permissions \
  --policy-document "file://$(render infra/manual/policy-ingest.json)"
