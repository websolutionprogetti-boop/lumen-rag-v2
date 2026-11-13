#!/usr/bin/env bash
# Cancella tutte le risorse di Lumen v2 create da crea_risorse.sh (non tocca il resto dell'account).
set -uo pipefail
REGIONE=eu-central-1
ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
BUCKET="lumen-v2-${ACCOUNT}"
export AWS_REGION=$REGIONE
aws lambda delete-function --function-name lumen-v2
aws iam delete-role-policy --role-name lumen-v2-lambda --policy-name lumen-v2-permessi
aws iam delete-role --role-name lumen-v2-lambda
aws dynamodb delete-table --table-name lumen-v2-contatori >/dev/null
aws s3 rm "s3://$BUCKET" --recursive && aws s3api delete-bucket --bucket "$BUCKET"
aws logs delete-log-group --log-group-name /aws/lambda/lumen-v2 2>/dev/null
echo "Risorse di Lumen v2 eliminate."
