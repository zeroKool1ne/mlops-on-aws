#!/usr/bin/env bash
# HTTP API, not REST API: same Lambda proxy integration, about a seventh of the
# price ($1.00 vs $3.50 per million) and a fraction of the configuration. The
# REST API's extra features - request validation, API keys, WAF integration -
# are not used here, so paying for them would be paying for nothing.
#
# Two routes to one integration. 'ANY /' serves the demo page; 'ANY /{proxy+}'
# catches everything else and lets FastAPI do its own routing, which is what
# keeps the API surface defined in one place (src/api/main.py) instead of split
# between the code and the gateway.
set -e

NAME=goldmlops-api
REGION=us-east-1
ACCOUNT=686699774218
FN_ARN="arn:aws:lambda:$REGION:$ACCOUNT:function:goldmlops-api"

API_ID=$(aws apigatewayv2 get-apis --query "Items[?Name=='$NAME'].ApiId | [0]" --output text)
if [[ "$API_ID" == "None" || -z "$API_ID" ]]; then
    API_ID=$(aws apigatewayv2 create-api --name "$NAME" --protocol-type HTTP \
        --description "Gold/USD forecasting API" \
        --query ApiId --output text)
    echo "--- API angelegt: $API_ID"
else
    echo "--- API existiert: $API_ID"
fi

INT_ID=$(aws apigatewayv2 get-integrations --api-id "$API_ID" \
    --query "Items[?IntegrationUri=='$FN_ARN'].IntegrationId | [0]" --output text)
if [[ "$INT_ID" == "None" || -z "$INT_ID" ]]; then
    INT_ID=$(aws apigatewayv2 create-integration --api-id "$API_ID" \
        --integration-type AWS_PROXY \
        --integration-uri "$FN_ARN" \
        --payload-format-version 2.0 \
        --timeout-in-millis 29000 \
        --query IntegrationId --output text)
fi
echo "--- Integration: $INT_ID"

for ROUTE in 'ANY /' 'ANY /{proxy+}'; do
    EXISTS=$(aws apigatewayv2 get-routes --api-id "$API_ID" \
        --query "Items[?RouteKey=='$ROUTE'].RouteId | [0]" --output text)
    [[ "$EXISTS" == "None" || -z "$EXISTS" ]] && \
        aws apigatewayv2 create-route --api-id "$API_ID" \
            --route-key "$ROUTE" --target "integrations/$INT_ID" >/dev/null
done
echo "--- Routen: $(aws apigatewayv2 get-routes --api-id "$API_ID" --query 'Items[].RouteKey' --output text)"

# $default stage with auto-deploy: no manual deployment step, ever.
aws apigatewayv2 get-stage --api-id "$API_ID" --stage-name '$default' >/dev/null 2>&1 \
    || aws apigatewayv2 create-stage --api-id "$API_ID" --stage-name '$default' \
        --auto-deploy >/dev/null

# Throttling. The API is public so it can be demonstrated, so it needs a
# ceiling: a runaway script should cost cents, not dollars.
aws apigatewayv2 update-stage --api-id "$API_ID" --stage-name '$default' \
    --default-route-settings 'ThrottlingBurstLimit=20,ThrottlingRateLimit=10' >/dev/null

# API Gateway may invoke this function. Resource-based policy on the Lambda -
# the mirror image of the role's trust policy, and the same idea: the caller
# needs permission from the callee.
aws lambda get-policy --function-name goldmlops-api --output text 2>/dev/null | grep -q apigateway-invoke \
    || aws lambda add-permission --function-name goldmlops-api \
        --statement-id apigateway-invoke \
        --action lambda:InvokeFunction \
        --principal apigateway.amazonaws.com \
        --source-arn "arn:aws:execute-api:$REGION:$ACCOUNT:$API_ID/*/*" >/dev/null

echo
echo "=== URL ==="
aws apigatewayv2 get-api --api-id "$API_ID" --query ApiEndpoint --output text
