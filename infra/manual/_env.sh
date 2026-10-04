# Shared setup for the scripts in this directory. Source it, do not run it:
#
#     source "$(dirname "$0")/_env.sh"
#
# It exists so that no account number is written down anywhere in this
# repository. The scripts ask AWS who they are instead, which has two
# consequences worth having: the repository is safe to publish, and it runs
# unchanged in any account - including the one this project eventually moves
# to, which was previously a find-and-replace across nine files.
#
# The policy documents carry <ACCOUNT_ID> and are rendered to a temporary file
# at the moment they are used. IAM has no variables of its own, so a template
# is the only way to keep a literal account number out of them.

set -euo pipefail

ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
REGION=${AWS_REGION:-us-east-1}
PROJECT=goldmlops
BUCKET="$PROJECT-data-$ACCOUNT"
REGISTRY="$ACCOUNT.dkr.ecr.$REGION.amazonaws.com"
IMAGE="$REGISTRY/$PROJECT-api:latest"

# render <template.json> -> prints the path of a temporary file with the real
# account id substituted in. Used as: --policy-document "file://$(render ...)"
render () {
    local src="$1"
    local out="${TMPDIR:-/tmp}/rendered-$(basename "$src")"
    sed "s/<ACCOUNT_ID>/$ACCOUNT/g; s/<REGION>/$REGION/g" "$src" > "$out"
    printf '%s' "$out"
}
