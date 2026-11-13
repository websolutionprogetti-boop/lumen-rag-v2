#!/usr/bin/env bash
# Aggiorna solo il codice della funzione Lambda (non tocca documenti, indice, tabella, permessi o budget).
# Da lanciare in AWS CloudShell dopo aver caricato lumen-v2.zip (Azioni → Carica file).
set -euo pipefail
REGIONE=eu-central-1
export AWS_REGION=$REGIONE
ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
BUCKET="lumen-v2-${ACCOUNT}"
ZIP="${1:-lumen-v2.zip}"

aws s3 cp "$ZIP" "s3://$BUCKET/pacchetto/lumen-v2.zip"
aws lambda update-function-code --function-name lumen-v2 --s3-bucket "$BUCKET" --s3-key pacchetto/lumen-v2.zip >/dev/null
aws lambda wait function-updated --function-name lumen-v2
URL=$(aws lambda get-function-url-config --function-name lumen-v2 --query FunctionUrl --output text)
echo "Codice aggiornato. Prova: curl -s ${URL}api/salute"
