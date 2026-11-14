#!/usr/bin/env bash
# Confronto delle istruzioni dell'agente: stessa valutazione con la versione precedente e con quella nuova.
# Per ogni versione: 30 domande di controllo (scripts/valuta.py) e RAGAS (12 domande). Tutte le risposte
# finiscono anche su LangSmith, progetto "lumen-v2-valutazioni", con la versione nei metadati.
# Non consuma il tetto mensile del sito (il contatore su DynamoDB non viene usato). Costo: pochi centesimi.
# Dura 15-25 minuti: in CloudShell lanciarlo in sottofondo, nohup bash deploy/valuta_confronto.sh > confronto.log 2>&1 &
set -euo pipefail
export PYTHONUNBUFFERED=1
python3 -c "import langchain_core, langgraph, langchain_aws, rank_bm25" 2>/dev/null || {
  echo "Mancano le librerie del progetto. Prima:"
  echo "  python3 -m venv ~/venv-lumen && ~/venv-lumen/bin/pip install -q -r requirements-lambda.txt && source ~/venv-lumen/bin/activate"
  exit 1; }
export AWS_REGION=eu-central-1 LUMEN_MODALITA=bedrock
ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
export LUMEN_INDICE="s3://lumen-v2-${ACCOUNT}/indice" LUMEN_DOCUMENTI="s3://lumen-v2-${ACCOUNT}/documenti"
# La chiave LangSmith si legge dalla Lambda: non va scritta di nuovo.
LANGSMITH_API_KEY=$(aws lambda get-function-configuration --function-name lumen-v2 \
  --query Environment.Variables.LANGSMITH_API_KEY --output text)
if [ "$LANGSMITH_API_KEY" != "None" ]; then
  export LANGSMITH_API_KEY LUMEN_LANGSMITH=1 LANGSMITH_ENDPOINT=https://eu.api.smith.langchain.com \
         LANGSMITH_PROJECT=lumen-v2-valutazioni LUMEN_ORIGINE=valutazione
else
  unset LANGSMITH_API_KEY; echo "(LangSmith non attivo sulla Lambda: valutazione senza tracce)"
fi
[ -x /tmp/ragas/bin/python ] || { python3 -m venv /tmp/ragas && /tmp/ragas/bin/pip install -q -r requirements-ragas.txt; }
mkdir -p risultati
for V in "${@:-2026-11-13 2026-11-14}"; do
  for VER in $V; do
    echo; echo "================ istruzioni $VER"
    export LUMEN_PROMPT=$VER
    python3 scripts/valuta.py || true   # esce con 1 se un controllo fallisce: il confronto va avanti lo stesso
    mv valutazione.json "risultati/valutazione-$VER.json"
    python3 scripts/ragas_dati.py >/dev/null && /tmp/ragas/bin/python scripts/ragas_punteggi.py
    mv ragas_dati.json "risultati/ragas_dati-$VER.json"; mv ragas_risultati.json "risultati/ragas_risultati-$VER.json"
  done
done
python3 scripts/confronta.py
