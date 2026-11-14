#!/usr/bin/env bash
# Accende (o spegne) il tracciamento LangSmith sulla funzione Lambda, senza toccare le altre impostazioni.
#   bash deploy/attiva_langsmith.sh          chiede la chiave e accende il tracciamento
#   bash deploy/attiva_langsmith.sh spegni   toglie chiave e tracciamento
# La chiave si incolla quando richiesto: non compare sullo schermo, non finisce nella cronologia
# e non resta su disco (il file temporaneo viene cancellato subito).
set -euo pipefail
export AWS_REGION=eu-central-1
FUNZIONE=lumen-v2
TMP=$(mktemp); chmod 600 "$TMP"; trap 'rm -f "$TMP"' EXIT

ATTUALI=$(aws lambda get-function-configuration --function-name $FUNZIONE --query 'Environment.Variables' --output json)
if [ "${1:-}" = "spegni" ]; then
  echo "$ATTUALI" | jq -c '{Variables: (del(.LUMEN_LANGSMITH, .LANGSMITH_API_KEY, .LANGSMITH_ENDPOINT, .LANGSMITH_PROJECT))}' > "$TMP"
else
  read -rsp "Incolla la chiave LangSmith (inizia con lsv2_) e premi Invio: " CHIAVE; echo
  # L'incolla del terminale può aggiungere codici invisibili (ESC[200~ … ESC[201~) o spazi: si tolgono,
  # altrimenti LangSmith risponde "400 Bad Request" e le tracce non arrivano.
  CHIAVE=$(printf '%s' "$CHIAVE" | sed $'s/\e\[20[01]~//g' | tr -cd 'A-Za-z0-9_-')
  case "$CHIAVE" in lsv2_*) ;; *) echo "La chiave deve iniziare con lsv2_: niente è stato cambiato."; exit 1 ;; esac
  echo "$ATTUALI" | jq -c --arg k "$CHIAVE" '{Variables: (. + {LUMEN_LANGSMITH: "1", LANGSMITH_API_KEY: $k,
    LANGSMITH_ENDPOINT: "https://eu.api.smith.langchain.com", LANGSMITH_PROJECT: "lumen-v2"})}' > "$TMP"
  unset CHIAVE
fi
aws lambda update-function-configuration --function-name $FUNZIONE --environment "file://$TMP" >/dev/null
aws lambda wait function-updated --function-name $FUNZIONE
aws lambda get-function-configuration --function-name $FUNZIONE \
  --query 'Environment.Variables.{tracciamento: LUMEN_LANGSMITH, endpoint: LANGSMITH_ENDPOINT, progetto: LANGSMITH_PROJECT}' --output table
echo "Fatto. La chiave non viene mostrata."
