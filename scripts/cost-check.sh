#!/usr/bin/env bash
# Daily cost check: what is running, and what is it costing?
#
# Usage:
#   ./scripts/cost-check.sh              # uses AWS_PROFILE or "default"
#   ./scripts/cost-check.sh privat       # checks a specific profile
#   ./scripts/cost-check.sh privat --spend   # include the account-wide bill
#
# Read-only. Nothing here creates, modifies or deletes anything.
#
# The month-to-date spend breakdown is behind --spend on purpose. It reports
# the whole ACCOUNT, and development runs in a shared course account, where
# that is every participant's spend and none of this project's business. For
# what this project costs, use scripts/cost-report.py, which measures the
# goldmlops-* resources and prices them itself.
#
# The resource inventory is filtered to this project by default, behind
# --all-resources otherwise, for the same reason. It does not show money, but
# on a shared account it shows other people's clusters and load balancers by
# name, and those names are not ours to collect or repeat. Use it unfiltered
# only on an account you own.

set -uo pipefail

PROFILE="${1:-${AWS_PROFILE:-default}}"

SHOW_SPEND=0
SHOW_ALL=0
for arg in "$@"; do
  [[ "$arg" == "--spend" ]] && SHOW_SPEND=1
  [[ "$arg" == "--all-resources" ]] && SHOW_ALL=1
done

# Regions worth checking. Most accounts only ever use two or three, but a
# forgotten instance in an unused region is exactly the kind of thing that
# quietly bills for months.
REGIONS=(us-east-1 us-west-2 eu-central-1 eu-west-1)

RED=$'\033[31m'; YELLOW=$'\033[33m'; GREEN=$'\033[32m'; BOLD=$'\033[1m'; OFF=$'\033[0m'

aws_p() { aws --profile "$PROFILE" "$@"; }

echo "${BOLD}=== AWS cost check — profile: ${PROFILE} — $(date '+%Y-%m-%d %H:%M') ===${OFF}"

IDENTITY=$(aws_p sts get-caller-identity --query '[Account,Arn]' --output text 2>&1)
if [[ "$IDENTITY" == *"error"* || "$IDENTITY" == *"Unable"* ]]; then
  echo "${RED}Cannot authenticate with profile '${PROFILE}'.${OFF}"
  echo "Configured profiles: $(aws configure list-profiles 2>/dev/null | tr '\n' ' ')"
  exit 1
fi
echo "Account: ${IDENTITY}"
echo

# --- Month-to-date spend, broken down by service -------------------------
MONTH_START=$(date '+%Y-%m-01')
TOMORROW=$(date -v+1d '+%Y-%m-%d' 2>/dev/null || date -d tomorrow '+%Y-%m-%d')

if [[ $SHOW_SPEND -eq 0 ]]; then
  echo "${BOLD}--- Spend so far this month ---${OFF}"
  echo "  Skipped: this reports the whole account, which is shared."
  echo "  This project's own cost:  python scripts/cost-report.py"
  echo "  Account-wide anyway:      $0 ${PROFILE} --spend"
else
echo "${BOLD}--- Spend so far this month (from ${MONTH_START}) ---${OFF}"
aws_p ce get-cost-and-usage \
  --time-period "Start=${MONTH_START},End=${TOMORROW}" \
  --granularity MONTHLY --metrics UnblendedCost \
  --group-by Type=DIMENSION,Key=SERVICE --output json 2>/dev/null \
| python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
except Exception:
    print('  (Cost Explorer not accessible with this profile)'); sys.exit()
for r in d.get('ResultsByTime', []):
    rows = [(g['Keys'][0], float(g['Metrics']['UnblendedCost']['Amount'])) for g in r['Groups']]
    rows.sort(key=lambda x: -x[1])
    total = sum(v for _, v in rows)
    for name, amount in rows:
        if amount > 0.01:
            print(f'  {amount:9.2f} USD  {name}')
    print(f'  {\"-\"*9}')
    print(f'  {total:9.2f} USD  TOTAL')
"
fi
echo

# --- What is actually running right now ----------------------------------
if [[ $SHOW_ALL -eq 0 ]]; then
  echo "${BOLD}--- Billable resources: this project only ---${OFF}"
  for region in "${REGIONS[@]}"; do
    MINE=$(aws_p resourcegroupstaggingapi get-resources --region "$region" \
      --query 'ResourceTagMappingList[].ResourceARN' --output text 2>/dev/null \
      | tr '\t' '\n' | grep -i goldmlops || true)
    [[ -n "$MINE" ]] && { echo "${BOLD}[${region}]${OFF}"; printf '  %s\n' $MINE; }
  done
  echo
  echo "  Nothing billable of ours runs while idle - Lambda, S3 and ECR only."
  echo "  Measured cost:        python scripts/cost-report.py"
  echo "  Whole account anyway: $0 ${PROFILE} --all-resources"
  echo
  echo "Checked regions: ${REGIONS[*]}"
  exit 0
fi

echo "${BOLD}--- Billable resources currently running (WHOLE ACCOUNT) ---${OFF}"
echo "${YELLOW}On a shared account this lists other people's resources. Do not copy it anywhere.${OFF}"
FOUND=0

for region in "${REGIONS[@]}"; do
  OUTPUT=""

  # EC2 instances: the classic forgotten cost
  instances=$(aws_p ec2 describe-instances --region "$region" \
    --filters Name=instance-state-name,Values=running \
    --query 'Reservations[].Instances[].[InstanceId,InstanceType]' --output text 2>/dev/null)
  [[ -n "$instances" ]] && OUTPUT+="  EC2 running ($(echo "$instances" | wc -l | tr -d ' ')): $(echo "$instances" | awk '{print $2}' | sort | uniq -c | tr '\n' ' ')"$'\n'

  # EKS: expensive even with no workload — the control plane alone is ~$0.10/h
  clusters=$(aws_p eks list-clusters --region "$region" --query 'clusters' --output text 2>/dev/null)
  [[ -n "$clusters" && "$clusters" != "None" ]] && OUTPUT+="  EKS clusters: ${clusters}"$'\n'

  # Load balancers bill per hour whether or not traffic flows
  lbs=$(aws_p elbv2 describe-load-balancers --region "$region" \
    --query 'LoadBalancers[].LoadBalancerName' --output text 2>/dev/null)
  [[ -n "$lbs" && "$lbs" != "None" ]] && OUTPUT+="  Load balancers: ${lbs}"$'\n'

  # RDS instances bill continuously
  dbs=$(aws_p rds describe-db-instances --region "$region" \
    --query 'DBInstances[].[DBInstanceIdentifier,DBInstanceClass]' --output text 2>/dev/null)
  [[ -n "$dbs" ]] && OUTPUT+="  RDS: $(echo "$dbs" | tr '\n' ' ')"$'\n'

  # SageMaker real-time endpoints bill per hour. Serverless ones do not appear
  # as a cost when idle, but are listed here anyway so nothing is invisible.
  eps=$(aws_p sagemaker list-endpoints --region "$region" \
    --query 'Endpoints[].EndpointName' --output text 2>/dev/null)
  [[ -n "$eps" && "$eps" != "None" ]] && OUTPUT+="  ${RED}SageMaker endpoints: ${eps}${OFF}"$'\n'

  # Unattached Elastic IPs are billed precisely because they are unused
  eips=$(aws_p ec2 describe-addresses --region "$region" \
    --query 'Addresses[?AssociationId==null].PublicIp' --output text 2>/dev/null)
  [[ -n "$eips" && "$eips" != "None" ]] && OUTPUT+="  ${YELLOW}Unattached Elastic IPs (billed!): ${eips}${OFF}"$'\n'

  # NAT gateways: ~$32/month each, a notorious surprise
  nats=$(aws_p ec2 describe-nat-gateways --region "$region" \
    --filter Name=state,Values=available \
    --query 'NatGateways[].NatGatewayId' --output text 2>/dev/null)
  [[ -n "$nats" && "$nats" != "None" ]] && OUTPUT+="  ${YELLOW}NAT gateways (~\$32/mo each): ${nats}${OFF}"$'\n'

  if [[ -n "$OUTPUT" ]]; then
    echo "${BOLD}[${region}]${OFF}"
    printf '%s' "$OUTPUT"
    FOUND=1
  fi
done

[[ $FOUND -eq 0 ]] && echo "  ${GREEN}Nothing billable running in the checked regions.${OFF}"

echo
echo "Checked regions: ${REGIONS[*]}"
