"""Tracciamento facoltativo su LangSmith (osservabilità: ogni domanda diventa una traccia con i passi del grafo).

Si accende solo con LUMEN_LANGSMITH=1 e una chiave in LANGSMITH_API_KEY; senza, il codice si comporta come prima.
Non si usa LANGSMITH_TRACING=true di proposito: così il tracciatore è uno solo, il nostro, e passa sempre
dal filtro `nascondi`, che prima dell'invio:
- toglie gli oggetti interni (il ricercatore con l'indice);
- ripassa ogni testo nell'oscuramento dei dati personali (seconda rete di sicurezza: domanda, storia e
  documenti del visitatore sono già oscurati prima di arrivare al grafo).

Variabili d'ambiente:
  LUMEN_LANGSMITH=1                 accende il tracciamento
  LANGSMITH_API_KEY                 chiave del progetto LangSmith (mai nel codice)
  LANGSMITH_ENDPOINT                https://eu.api.smith.langchain.com per l'account in regione EU
  LANGSMITH_PROJECT                 nome del progetto (default "lumen-v2")
  LUMEN_ORIGINE                     "sito" (default) oppure "valutazione": finisce nei tag della traccia
"""
from __future__ import annotations

import logging
import os
from functools import lru_cache
from typing import Any

from .privacy import oscura

log = logging.getLogger("lumen")

_CHIAVI_DA_TOGLIERE = {"ricercatore"}


def attivo() -> bool:
    return os.getenv("LUMEN_LANGSMITH", "") == "1" and bool(os.getenv("LANGSMITH_API_KEY"))


def nascondi(valore: Any) -> Any:
    """Copia del valore pronta per LangSmith: senza oggetti interni e con i dati personali oscurati."""
    if isinstance(valore, str):
        return oscura(valore).testo
    if isinstance(valore, dict):
        return {k: ("[omesso]" if k in _CHIAVI_DA_TOGLIERE else nascondi(v)) for k, v in valore.items()}
    if isinstance(valore, (list, tuple)):
        return [nascondi(v) for v in valore]
    if hasattr(valore, "page_content"):  # Document di LangChain
        return {"page_content": nascondi(valore.page_content), "metadata": nascondi(dict(valore.metadata))}
    if hasattr(valore, "content") and hasattr(valore, "type"):  # messaggi di LangChain
        return {"type": valore.type, "content": nascondi(valore.content),
                "tool_calls": nascondi(getattr(valore, "tool_calls", []) or [])}
    if valore is None or isinstance(valore, (bool, int, float)):
        return valore
    return f"[{type(valore).__name__}]"


@lru_cache(maxsize=1)
def _tracciatore():
    from langchain_core.tracers.langchain import LangChainTracer
    from langsmith import Client

    # Tempi brevi: se LangSmith è lento o irraggiungibile la risposta al visitatore non deve aspettare.
    client = Client(hide_inputs=nascondi, hide_outputs=nascondi, hide_metadata=False, timeout_ms=3000,
                    retry_config={"max_retries": 1})
    return LangChainTracer(client=client, project_name=os.getenv("LANGSMITH_PROJECT", "lumen-v2")), client


def config_traccia(lingua: str, versione_prompt: str) -> dict:
    """Pezzo di configurazione da passare a grafo.invoke: callbacks, nome, tag e metadati della traccia."""
    if not attivo():
        return {}
    try:
        tracciatore, _ = _tracciatore()
    except Exception:  # noqa: BLE001 — il tracciamento non deve mai bloccare una risposta
        log.exception("LangSmith non disponibile")
        return {}
    origine = os.getenv("LUMEN_ORIGINE", "sito")
    return {"callbacks": [tracciatore], "run_name": "lumen-v2",
            "tags": ["lumen-v2", lingua, origine, f"prompt-{versione_prompt}"],
            "metadata": {"lingua": lingua, "origine": origine, "versione_prompt": versione_prompt}}


def svuota() -> None:
    """Invia subito le tracce in coda: su Lambda il processo si congela dopo la risposta."""
    if not attivo():
        return
    try:
        tracciatore, client = _tracciatore()
        tracciatore.wait_for_futures()
        client.flush()
    except Exception:  # noqa: BLE001
        log.exception("Invio delle tracce a LangSmith non riuscito")
