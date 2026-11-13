#!/usr/bin/env bash
# Crea su AWS (regione Francoforte) tutto quello che serve a Lumen v2. Da lanciare in AWS CloudShell
# dalla cartella del progetto. Ogni risorsa ha il prefisso "lumen-v2" per riconoscerla e cancellarla.
#
#   S3          lumen-v2-<account>     documenti e indice (privato, mai pubblico)
#   DynamoDB    lumen-v2-contatori     contatore mensile delle domande (tetto di spesa)
#   IAM         lumen-v2-lambda        permessi minimi: Claude Haiku/Nova/Titan su Bedrock, lettura S3, contatore
#   Lambda      lumen-v2               il codice Python + LangChain, con indirizzo web (Function URL)
#
# Costo previsto: Lambda, S3 e DynamoDB restano nelle quote gratuite; Bedrock pochi centesimi (crediti AWS).
set -euo pipefail

REGIONE=eu-central-1
ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
BUCKET="lumen-v2-${ACCOUNT}"
TABELLA=lumen-v2-contatori
RUOLO=lumen-v2-lambda
FUNZIONE=lumen-v2
ORIGINE="https://websolution-progetti.pages.dev"
TETTO_MENSILE=300
export AWS_REGION=$REGIONE

echo "== 1/6 Bucket S3 privato per documenti e indice"
aws s3api create-bucket --bucket "$BUCKET" --region $REGIONE \
  --create-bucket-configuration LocationConstraint=$REGIONE >/dev/null 2>&1 || echo "   (esiste già)"
aws s3api put-public-access-block --bucket "$BUCKET" \
  --public-access-block-configuration BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
aws s3 cp documenti/ "s3://$BUCKET/documenti/" --recursive --exclude "*" --include "documenti_*.json"

echo "== 2/6 Indice (embeddings Titan v2) salvato su S3"
pip install --quiet -r requirements-lambda.txt
LUMEN_INDICE="s3://$BUCKET/indice" LUMEN_DOCUMENTI="s3://$BUCKET/documenti" python3 scripts/costruisci_indice.py

echo "== 3/6 Tabella DynamoDB per il tetto mensile"
aws dynamodb create-table --table-name $TABELLA --billing-mode PAY_PER_REQUEST \
  --attribute-definitions AttributeName=mese,AttributeType=S --key-schema AttributeName=mese,KeyType=HASH \
  --region $REGIONE >/dev/null 2>&1 || echo "   (esiste già)"

echo "== 4/6 Ruolo IAM con permessi minimi"
cat > /tmp/fiducia.json <<JSON
{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"lambda.amazonaws.com"},"Action":"sts:AssumeRole"}]}
JSON
cat > /tmp/permessi.json <<JSON
{"Version":"2012-10-17","Statement":[
 {"Sid":"Modelli","Effect":"Allow","Action":["bedrock:InvokeModel","bedrock:InvokeModelWithResponseStream"],
  "Resource":["arn:aws:bedrock:${REGIONE}:${ACCOUNT}:inference-profile/eu.anthropic.claude-haiku-4-5-20251001-v1:0",
              "arn:aws:bedrock:${REGIONE}:${ACCOUNT}:inference-profile/eu.amazon.nova-lite-v1:0",
              "arn:aws:bedrock:eu-*::foundation-model/anthropic.claude-haiku-4-5-20251001-v1:0",
              "arn:aws:bedrock:eu-*::foundation-model/amazon.nova-lite-v1:0",
              "arn:aws:bedrock:${REGIONE}::foundation-model/amazon.titan-embed-text-v2:0"]},
 {"Sid":"Documenti","Effect":"Allow","Action":"s3:GetObject","Resource":"arn:aws:s3:::${BUCKET}/*"},
 {"Sid":"Contatore","Effect":"Allow","Action":"dynamodb:UpdateItem","Resource":"arn:aws:dynamodb:${REGIONE}:${ACCOUNT}:table/${TABELLA}"},
 {"Sid":"Log","Effect":"Allow","Action":["logs:CreateLogGroup","logs:CreateLogStream","logs:PutLogEvents"],"Resource":"*"}]}
JSON
aws iam create-role --role-name $RUOLO --assume-role-policy-document file:///tmp/fiducia.json >/dev/null 2>&1 || echo "   (esiste già)"
aws iam put-role-policy --role-name $RUOLO --policy-name lumen-v2-permessi --policy-document file:///tmp/permessi.json
RUOLO_ARN=$(aws iam get-role --role-name $RUOLO --query Role.Arn --output text)

echo "== 5/6 Pacchetto della funzione (zip)"
rm -rf deploy/pacchetto deploy/lumen-v2.zip
pip install --quiet --target deploy/pacchetto -r requirements-lambda.txt \
  --platform manylinux_2_28_x86_64 --platform manylinux2014_x86_64 --implementation cp --python-version 3.13 --only-binary=:all:
cp -r app lambda_handler.py deploy/pacchetto/
(cd deploy/pacchetto && zip -qr9 ../lumen-v2.zip . -x "*__pycache__*")
aws s3 cp deploy/lumen-v2.zip "s3://$BUCKET/pacchetto/lumen-v2.zip"

echo "== 6/6 Funzione Lambda con indirizzo web"
AMBIENTE="Variables={LUMEN_MODALITA=bedrock,LUMEN_INDICE=s3://$BUCKET/indice,LUMEN_DOCUMENTI=s3://$BUCKET/documenti,LUMEN_TABELLA=$TABELLA,LUMEN_TETTO_MENSILE=$TETTO_MENSILE,LUMEN_ORIGINI=$ORIGINE}"
if aws lambda get-function --function-name $FUNZIONE >/dev/null 2>&1; then
  aws lambda update-function-code --function-name $FUNZIONE --s3-bucket "$BUCKET" --s3-key pacchetto/lumen-v2.zip >/dev/null
  aws lambda wait function-updated --function-name $FUNZIONE
  aws lambda update-function-configuration --function-name $FUNZIONE --environment "$AMBIENTE" >/dev/null
else
  sleep 10  # il ruolo appena creato impiega qualche secondo a essere utilizzabile
  aws lambda create-function --function-name $FUNZIONE --runtime python3.13 --architectures x86_64 \
    --role "$RUOLO_ARN" --handler lambda_handler.handler --memory-size 1024 --timeout 30 \
    --code S3Bucket="$BUCKET",S3Key=pacchetto/lumen-v2.zip --environment "$AMBIENTE" >/dev/null
  aws lambda wait function-active-v2 --function-name $FUNZIONE
  aws lambda create-function-url-config --function-name $FUNZIONE --auth-type NONE \
    --cors "AllowOrigins=$ORIGINE,AllowMethods=GET,POST,AllowHeaders=content-type,MaxAge=3600" >/dev/null
  aws lambda add-permission --function-name $FUNZIONE --statement-id url-pubblico \
    --action lambda:InvokeFunctionUrl --principal "*" --function-url-auth-type NONE >/dev/null
  aws lambda add-permission --function-name $FUNZIONE --statement-id url-pubblico-invoke \
    --action lambda:InvokeFunction --principal "*" --invoked-via-function-url >/dev/null 2>&1 || true
fi
URL=$(aws lambda get-function-url-config --function-name $FUNZIONE --query FunctionUrl --output text)
echo
echo "Fatto. Indirizzo dell'API: $URL"
echo "Prova:  curl -s ${URL}api/salute"
