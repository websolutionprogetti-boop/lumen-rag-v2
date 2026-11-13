"""RAGAS, passo 2: calcola i punteggi sulle risposte salvate da ragas_dati.py.
Il "giudice" è Claude Haiku su Bedrock; per la pertinenza servono anche gli embeddings Titan.

Metriche (da 0 a 1, più alto è meglio):
- faithfulness       la risposta dice solo cose presenti nei frammenti trovati (niente invenzioni)
- answer_relevancy   la risposta risponde davvero alla domanda
- context_precision  i frammenti utili sono in cima a quelli trovati
- context_recall     i frammenti trovati contengono tutto quello che serve per il riferimento

Uso (in un ambiente separato, perché RAGAS 0.4 usa una versione precedente di LangChain):
  python3 -m venv /tmp/ragas && /tmp/ragas/bin/pip install -r requirements-ragas.txt
  /tmp/ragas/bin/python scripts/ragas_punteggi.py
Costo: qualche centesimo (circa 150 chiamate brevi a Claude Haiku).
"""
import json
import os
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

from langchain_aws import BedrockEmbeddings, ChatBedrockConverse  # noqa: E402
from ragas import EvaluationDataset, evaluate  # noqa: E402
from ragas.embeddings import LangchainEmbeddingsWrapper  # noqa: E402
from ragas.llms import LangchainLLMWrapper  # noqa: E402
from ragas.metrics import (Faithfulness, LLMContextPrecisionWithReference, LLMContextRecall,  # noqa: E402
                           ResponseRelevancy)
from ragas.run_config import RunConfig  # noqa: E402

REGIONE = os.getenv("AWS_REGION", "eu-central-1")
GIUDICE = os.getenv("LUMEN_MODELLO", "eu.anthropic.claude-haiku-4-5-20251001-v1:0")
EMBEDDINGS = os.getenv("LUMEN_EMBEDDINGS", "amazon.titan-embed-text-v2:0")


def main() -> None:
    righe = json.loads(Path("ragas_dati.json").read_text(encoding="utf-8"))
    dataset = EvaluationDataset.from_list([{k: r[k] for k in ("user_input", "response", "retrieved_contexts", "reference")}
                                          for r in righe])
    llm = LangchainLLMWrapper(ChatBedrockConverse(model=GIUDICE, region_name=REGIONE, temperature=0, max_tokens=2048))
    emb = LangchainEmbeddingsWrapper(BedrockEmbeddings(model_id=EMBEDDINGS, region_name=REGIONE))
    metriche = [Faithfulness(), ResponseRelevancy(), LLMContextPrecisionWithReference(), LLMContextRecall()]
    risultato = evaluate(dataset, metrics=metriche, llm=llm, embeddings=emb,
                         run_config=RunConfig(max_workers=1, timeout=180, max_retries=12, max_wait=90))
    tabella = risultato.to_pandas()
    colonne = [c for c in tabella.columns if c not in ("user_input", "response", "retrieved_contexts", "reference")]
    medie = {c: round(float(tabella[c].mean()), 3) for c in colonne}
    dettagli = [{"domanda": r["user_input"], **{c: (None if tabella.loc[i, c] != tabella.loc[i, c] else round(float(tabella.loc[i, c]), 3))
                                               for c in colonne}} for i, r in enumerate(righe)]
    Path("ragas_risultati.json").write_text(json.dumps({"medie": medie, "domande": dettagli}, ensure_ascii=False, indent=2),
                                            encoding="utf-8")
    print("\nPunteggi medi (0-1):")
    for c, v in medie.items():
        print(f"  {c:40s} {v}")
    print("\nDettaglio per domanda in ragas_risultati.json")


if __name__ == "__main__":
    main()
