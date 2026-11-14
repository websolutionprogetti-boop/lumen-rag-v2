"""RAGAS, controllo della misura: answer relevancy con le istruzioni del giudice adattate all'italiano.

Perché: ResponseRelevancy chiede al giudice di ricavare dalla risposta alcune domande e le confronta (embeddings)
con la domanda vera. Con le istruzioni standard, in inglese, da una risposta italiana escono domande in inglese,
e il confronto tra lingue diverse abbassa il punteggio anche quando la risposta è giusta: il 14/11 le 3 domande
in inglese valevano circa 0,55, le 9 in italiano circa 0,29.

Questo script riusa le risposte già salvate (risultati/ragas_dati-<versione>.json, nessuna nuova domanda
all'agente) e ricalcola solo la pertinenza delle domande italiane con le istruzioni tradotte da RAGAS
(adapt_prompts). Le domande inglesi tengono il punteggio standard.

Uso:  /tmp/ragas/bin/python scripts/ragas_pertinenza_it.py 2026-11-13 2026-11-14
Costo: meno di un centesimo per versione.
"""
import asyncio
import json
import os
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

from langchain_aws import BedrockEmbeddings, ChatBedrockConverse  # noqa: E402
from ragas import EvaluationDataset, evaluate  # noqa: E402
from ragas.embeddings import LangchainEmbeddingsWrapper  # noqa: E402
from ragas.llms import LangchainLLMWrapper  # noqa: E402
from ragas.metrics import ResponseRelevancy  # noqa: E402
from ragas.run_config import RunConfig  # noqa: E402

REGIONE = os.getenv("AWS_REGION", "eu-central-1")
GIUDICE = os.getenv("LUMEN_MODELLO", "eu.anthropic.claude-haiku-4-5-20251001-v1:0")
EMBEDDINGS = os.getenv("LUMEN_EMBEDDINGS", "amazon.titan-embed-text-v2:0")
R = Path("risultati")


def main(versioni: list[str]) -> None:
    llm = LangchainLLMWrapper(ChatBedrockConverse(model=GIUDICE, region_name=REGIONE, temperature=0, max_tokens=2048))
    emb = LangchainEmbeddingsWrapper(BedrockEmbeddings(model_id=EMBEDDINGS, region_name=REGIONE))
    metrica = ResponseRelevancy()
    metrica.set_prompts(**asyncio.run(metrica.adapt_prompts(language="italian", llm=llm, adapt_instruction=True)))
    riepilogo = {}
    for v in versioni:
        righe = json.loads((R / f"ragas_dati-{v}.json").read_text(encoding="utf-8"))
        standard = json.loads((R / f"ragas_risultati-{v}.json").read_text(encoding="utf-8"))["domande"]
        italiane = [r for r in righe if r["lingua"] == "it"]
        dataset = EvaluationDataset.from_list([{k: r[k] for k in ("user_input", "response", "retrieved_contexts", "reference")}
                                               for r in italiane])
        tabella = evaluate(dataset, metrics=[metrica], llm=llm, embeddings=emb,
                           run_config=RunConfig(max_workers=1, timeout=180, max_retries=12, max_wait=90)).to_pandas()
        adattati = dict(zip(tabella["user_input"], tabella["answer_relevancy"]))
        punteggi = []
        for r, s in zip(righe, standard):
            valore = adattati.get(r["user_input"]) if r["lingua"] == "it" else s.get("answer_relevancy")
            punteggi.append({"domanda": r["user_input"], "lingua": r["lingua"],
                             "standard": s.get("answer_relevancy"), "adattata": None if valore is None else round(float(valore), 3)})
        media = round(sum(p["adattata"] or 0 for p in punteggi) / len(punteggi), 3)
        riepilogo[v] = media
        (R / f"ragas_pertinenza_it-{v}.json").write_text(
            json.dumps({"media": media, "domande": punteggi}, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n== istruzioni {v}: answer relevancy con giudice in italiano = {media}")
        for p in punteggi:
            print(f"   {p['standard']!s:>6} -> {p['adattata']!s:>6}  [{p['lingua']}] {p['domanda'][:55]}")
    print("\nRiepilogo:", riepilogo)


if __name__ == "__main__":
    main(sys.argv[1:] or ["2026-11-13", "2026-11-14"])
