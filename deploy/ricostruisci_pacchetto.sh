#!/usr/bin/env bash
# Prepara deploy/lumen-v2.zip in CloudShell senza caricare i 130 MB dal PC: scarica il pacchetto già
# pubblicato sulla Lambda (librerie comprese), ci mette sopra app/ e lambda_handler.py di questa cartella
# e lo ricomprime. Poi: bash deploy/aggiorna_codice.sh deploy/lumen-v2.zip
set -euo pipefail
export AWS_REGION=eu-central-1
LAVORO=$(mktemp -d); trap 'rm -rf "$LAVORO"' EXIT
URL=$(aws lambda get-function --function-name lumen-v2 --query Code.Location --output text)
curl -s -o "$LAVORO/attuale.zip" "$URL"
mkdir "$LAVORO/pacchetto" && unzip -q "$LAVORO/attuale.zip" -d "$LAVORO/pacchetto"
rm -rf "$LAVORO/pacchetto/app" && cp -r app lambda_handler.py "$LAVORO/pacchetto/"
rm -f deploy/lumen-v2.zip
(cd "$LAVORO/pacchetto" && zip -qr9 "$OLDPWD/deploy/lumen-v2.zip" . -x "*__pycache__*")
ls -lh deploy/lumen-v2.zip
