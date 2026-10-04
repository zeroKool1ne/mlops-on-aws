#!/usr/bin/env bash
# Dashboard and alarms.
#
# The alarms are chosen for the failure modes this system actually has, not for
# a tidy set of four. Three of them catch something going wrong loudly. The
# fourth catches the one that goes wrong quietly: ingestion simply stopping.
# Nothing errors in that case - the feature table just stops growing and the
# model keeps serving a world that is weeks old. "No invocation in 36 hours" is
# the only way to see it.
set -e

REGION=us-east-1
ACCOUNT=686699774218
API_ID=$(aws apigatewayv2 get-apis --query "Items[?Name=='goldmlops-api'].ApiId | [0]" --output text)

# SNS topic for alarm actions. Subscribing an address is left to a human: it
# sends a confirmation mail that only the owner of the inbox can accept.
TOPIC=$(aws sns create-topic --name goldmlops-alerts --query TopicArn --output text)
echo "--- SNS: $TOPIC"

alarm () {
  NAME=$1; DESC=$2; shift 2
  aws cloudwatch put-metric-alarm \
    --alarm-name "$NAME" \
    --alarm-description "$DESC" \
    --alarm-actions "$TOPIC" \
    --treat-missing-data notBreaching \
    "$@"
  echo "    $NAME"
}

echo "--- Alarme:"

alarm goldmlops-api-5xx \
  "The public API returned a server error. Anything above zero is a user seeing a failure." \
  --namespace AWS/ApiGateway --metric-name 5xx --statistic Sum \
  --dimensions Name=ApiId,Value="$API_ID" \
  --period 300 --evaluation-periods 1 --threshold 0 \
  --comparison-operator GreaterThanThreshold

alarm goldmlops-api-errors \
  "The API Lambda raised. Distinct from a 5xx: this fires even when the gateway never sees the response." \
  --namespace AWS/Lambda --metric-name Errors --statistic Sum \
  --dimensions Name=FunctionName,Value=goldmlops-api \
  --period 300 --evaluation-periods 1 --threshold 0 \
  --comparison-operator GreaterThanThreshold

alarm goldmlops-ingest-errors \
  "A scheduled ingestion failed. The scheduler retries three times, so this means all of them failed." \
  --namespace AWS/Lambda --metric-name Errors --statistic Sum \
  --dimensions Name=FunctionName,Value=goldmlops-ingest \
  --period 3600 --evaluation-periods 1 --threshold 0 \
  --comparison-operator GreaterThanThreshold

# The silent one, and the two settings on it that are easy to get wrong.
#
# treat-missing-data must be BREACHING: no data points at all is precisely the
# condition being detected. On the default (notBreaching) this alarm would stay
# green forever exactly when ingestion had stopped - the failure it exists for.
#
# Four days, not two. The schedule runs Monday to Friday, so the normal gap
# across a weekend is Friday 23:30 to Monday 23:30 - seventy-two hours of
# silence that is entirely correct. An alarm at 48 hours would fire every
# Sunday, and an alarm that cries wolf weekly is worse than no alarm, because
# people learn to close it without looking.
aws cloudwatch put-metric-alarm \
  --alarm-name goldmlops-ingest-silent \
  --alarm-description "No ingestion for four days. This is the failure that looks like success: nothing errors, the feature table just stops growing and the model serves a world that is weeks old. Four days clears the normal 72-hour weekend gap." \
  --alarm-actions "$TOPIC" \
  --namespace AWS/Lambda --metric-name Invocations --statistic Sum \
  --dimensions Name=FunctionName,Value=goldmlops-ingest \
  --period 86400 --evaluation-periods 4 --datapoints-to-alarm 4 --threshold 1 \
  --comparison-operator LessThanThreshold \
  --treat-missing-data breaching
echo "    goldmlops-ingest-silent"

echo "--- Dashboard:"
cat > /tmp/dashboard.json <<JSON
{"widgets":[
 {"type":"metric","x":0,"y":0,"width":12,"height":6,"properties":{
   "title":"Lambda — invocations","region":"$REGION","stat":"Sum","period":300,
   "metrics":[["AWS/Lambda","Invocations","FunctionName","goldmlops-api"],
              [".",".",".","goldmlops-ingest"]]}},
 {"type":"metric","x":12,"y":0,"width":12,"height":6,"properties":{
   "title":"Lambda — errors (flat zero is the goal)","region":"$REGION","stat":"Sum","period":300,
   "metrics":[["AWS/Lambda","Errors","FunctionName","goldmlops-api"],
              [".",".",".","goldmlops-ingest"]]}},
 {"type":"metric","x":0,"y":6,"width":12,"height":6,"properties":{
   "title":"API latency — p50 vs p99 (the gap is the cold starts)","region":"$REGION","period":300,
   "metrics":[["AWS/Lambda","Duration","FunctionName","goldmlops-api",{"stat":"p50","label":"p50"}],
              ["...",{"stat":"p99","label":"p99"}],
              ["...",{"stat":"Maximum","label":"max"}]]}},
 {"type":"metric","x":12,"y":6,"width":12,"height":6,"properties":{
   "title":"API Gateway — requests and failures","region":"$REGION","stat":"Sum","period":300,
   "metrics":[["AWS/ApiGateway","Count","ApiId","$API_ID"],
              [".","4xx",".","."],
              [".","5xx",".","."]]}},
 {"type":"metric","x":0,"y":12,"width":12,"height":6,"properties":{
   "title":"Ingestion duration — watch this drift upward","region":"$REGION","period":86400,
   "metrics":[["AWS/Lambda","Duration","FunctionName","goldmlops-ingest",{"stat":"Maximum"}]]}},
 {"type":"metric","x":12,"y":12,"width":12,"height":6,"properties":{
   "title":"Data lake size","region":"$REGION","period":86400,"stat":"Average",
   "metrics":[["AWS/S3","BucketSizeBytes","BucketName","goldmlops-data-$ACCOUNT","StorageType","StandardStorage"]]}}
]}
JSON
aws cloudwatch put-dashboard --dashboard-name goldmlops \
  --dashboard-body file:///tmp/dashboard.json --output text
echo
echo "=== Ergebnis ==="
aws cloudwatch describe-alarms --alarm-name-prefix goldmlops \
  --query 'MetricAlarms[].[AlarmName,StateValue]' --output text
echo "Dashboard: https://$REGION.console.aws.amazon.com/cloudwatch/home?region=$REGION#dashboards/dashboard/goldmlops"
