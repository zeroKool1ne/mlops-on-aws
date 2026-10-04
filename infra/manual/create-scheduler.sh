#!/usr/bin/env bash
source "$(dirname "$0")/_env.sh"

aws iam create-role \
    --role-name goldmlops-scheduler \
    --assume-role-policy-document "file://$(render infra/manual/trust-scheduler.json)"

aws iam put-role-policy \
    --role-name goldmlops-scheduler \
    --policy-name invoke-ingest \
    --policy-document "file://$(render infra/manual/policy-scheduler.json)"

aws scheduler create-schedule \
    --name goldmlops-daily-ingest \
    --schedule-expression 'cron(30 23 ? * MON-FRI *)' \
    --schedule-expression-timezone UTC \
    --flexible-time-window '{"Mode":"OFF"}' \
    --target "{
            \"Arn\":\"arn:aws:lambda:$REGION:$ACCOUNT:function:$PROJECT-ingest\",
            \"RoleArn\":\"arn:aws:iam::$ACCOUNT:role/$PROJECT-scheduler\",
            \"RetryPolicy\":{\"MaximumRetryAttempts\":3,\"MaximumEventAgeInSeconds\":3600}
    }"