#!/usr/bin/env bash
# Cancella tutte le risorse di Lumen v2 create da crea_risorse.sh (non tocca il resto dell'account).
set -uo pipefail
REGIONE=eu-central-1
ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
BUCKET="lumen-v2-${ACCOUNT}"
export AWS_REGION=$REGIONE
# blocco automatico di Bedrock collegato al budget
for ID in $(aws budgets describe-budget-actions-for-budget --account-id $ACCOUNT --budget-name tetto-rag --query 'Actions[].ActionId' --output text 2>/dev/null); do
  aws budgets delete-budget-action --account-id $ACCOUNT --budget-name tetto-rag --action-id $ID >/dev/null
done
aws iam detach-role-policy --role-name lumen-v2-lambda --policy-arn arn:aws:iam::$ACCOUNT:policy/lumen-v2-blocca-bedrock 2>/dev/null
aws iam delete-role-policy --role-name lumen-v2-budget-azioni --policy-name lumen-v2-solo-blocco
aws iam delete-role --role-name lumen-v2-budget-azioni
aws iam delete-policy --policy-arn arn:aws:iam::$ACCOUNT:policy/lumen-v2-blocca-bedrock
aws lambda delete-function --function-name lumen-v2
aws iam delete-role-policy --role-name lumen-v2-lambda --policy-name lumen-v2-permessi
aws iam delete-role --role-name lumen-v2-lambda
aws dynamodb delete-table --table-name lumen-v2-contatori >/dev/null
aws s3 rm "s3://$BUCKET" --recursive && aws s3api delete-bucket --bucket "$BUCKET"
aws logs delete-log-group --log-group-name /aws/lambda/lumen-v2 2>/dev/null
echo "Risorse di Lumen v2 eliminate."
