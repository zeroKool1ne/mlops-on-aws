#!/usr/bin/env bash

set -e

aws iam create-role \
    --role-name goldmlops-scheduler \
    --assume-role-policy-document file://infra/manual/trust-scheduler.json

aws iam put-role-policy \
    --role-name goldmlops-scheduler \
    --policy-name invoke-ingest \
    --policy-document file://infra/manual/policy-scheduler.json

aws scheduler create-schedule \
    --name goldmlops-daily-ingest \
    --schedule-expression 'cron(30 23 ? * MON-FRI *)' \
    --schedule-expression-timezone UTC \
    --flexible-time-window '{"Mode":"OFF"}' \
    --target '{
            "Arn":"arn:aws:lambda:us-east-1:686699774218:function:goldmlops-ingest",
            "RoleArn":"arn:aws:iam::686699774218:role/goldmlops-scheduler",
            "RetryPolicy":{"MaximumRetryAttempts":3, "MaximumEventAgeInSeconds":3600}
    }'