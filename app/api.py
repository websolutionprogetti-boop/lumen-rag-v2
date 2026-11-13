"""API FastAPI dell'assistente. Documentazione automatica su /docs (OpenAPI).

Endpoint:
- POST /api/chiedi    domanda -> risposta con fonti (stesso formato della v1)
- GET  /api/documenti elenco dei documenti dello studio
- GET  /api/salute    controllo di funzionamento
"""
from __future__ import annotations

import logging
import os
from functools import lru_cache
from typing import Literal

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .agente import costruisci_grafo, rispondi
from .config import impostazioni
from .documenti import carica_documenti
from .limiti import LimiteAlMinuto, TettoMensile
from .modelli import crea_modello
from .ricerca import Indice, Ricercatore, crea_embeddings

log = logging.getLogger("lumen")

MESSAGGI = {
    "it": {
        "vuota": "Scrivi una domanda.",
        "lunga": "La domanda è troppo lunga (massimo 500 caratteri).",
        "troppe": "Troppe richieste in questo momento. Riprova tra un minuto.",
        "tetto": "La demo ha raggiunto il numero massimo di domande di questo mese ed è in pausa: tornerà disponibile il mese prossimo.",
        "irraggiungibile": "L'assistente non è raggiungibile in questo momento. Riprova più tardi.",
    },
    "en": {
        "vuota": "Please write a question.",
        "lunga": "The question is too long (maximum 500 characters).",
        "troppe": "Too many requests right now. Please try again in a minute.",
        "tetto": "The demo has reached this month's question limit and is paused: it will be available again next month.",
        "irraggiungibile": "The assistant can't be reached right now. Please try again later.",
    },
}


class Messaggio(BaseModel):
    ruolo: Literal["utente", "assistente"]
    testo: str = Field(max_length=4000)


class DocumentoVisitatore(BaseModel):
    titolo: str | None = Field(default=None, max_length=200)
    testo: str = Field(max_length=20_000)


class Domanda(BaseModel):
    domanda: str = Field(description="La domanda del visitatore (massimo 500 caratteri).", max_length=2000)
    lingua: Literal["it", "en"] = "it"
    storia: list[Messaggio] = Field(default_factory=list, max_length=20)
    documenti: list[DocumentoVisitatore] = Field(default_factory=list, max_length=5)


@lru_cache(maxsize=1)
def risorse():
    """Caricate una volta per istanza (in Lambda: al primo avvio, poi riusate)."""
    imp = impostazioni()
    embeddings = crea_embeddings(imp)
    ricercatori = {lingua: Ricercatore(Indice.carica(imp.indice, lingua), embeddings) for lingua in ("it", "en")}
    grafo = costruisci_grafo(crea_modello(imp))
    return imp, ricercatori, grafo, TettoMensile(imp.tetto_mensile, imp.tabella_contatori, imp.regione), \
        LimiteAlMinuto(imp.domande_al_minuto)


def crea_app() -> FastAPI:
    imp = impostazioni()
    app = FastAPI(title="Lumen v2 — assistente RAG (demo)", version="2.0.0",
                  description="Assistente della segreteria di uno studio dentistico FITTIZIO. "
                              "Python + LangChain + LangGraph, Claude Haiku su Amazon Bedrock.")
    # Su Lambda il CORS lo gestisce l'indirizzo della funzione (Function URL): aggiungerlo anche qui
    # duplicherebbe le intestazioni e il browser rifiuterebbe la risposta.
    if not os.getenv("AWS_LAMBDA_FUNCTION_NAME"):
        app.add_middleware(CORSMiddleware, allow_origins=list(imp.origini_consentite),
                           allow_methods=["GET", "POST"], allow_headers=["content-type"])

    @app.middleware("http")
    async def intestazioni_sicurezza(request: Request, call_next):
        risposta = await call_next(request)
        risposta.headers["x-content-type-options"] = "nosniff"
        risposta.headers["cache-control"] = "no-store"
        risposta.headers["referrer-policy"] = "strict-origin-when-cross-origin"
        return risposta

    @app.get("/api/salute")
    def salute():
        return {"stato": "ok", "versione": "2.0.0"}

    @app.get("/api/documenti")
    def documenti(lingua: Literal["it", "en"] = "it"):
        return [{"id": d["id"], "titolo": d["titolo"]} for d in carica_documenti(imp.cartella_documenti, lingua)]

    @app.post("/api/chiedi")
    def chiedi(corpo: Domanda, request: Request):
        T = MESSAGGI[corpo.lingua]
        if not corpo.domanda.strip():
            return JSONResponse({"errore": T["vuota"]}, 400)
        if len(corpo.domanda.strip()) > 500:
            return JSONResponse({"errore": T["lunga"]}, 400)
        _, ricercatori, grafo, tetto, al_minuto = risorse()
        visitatore = request.headers.get("x-forwarded-for", "").split(",")[0].strip() or (
            request.client.host if request.client else "sconosciuto")
        if al_minuto.troppe(visitatore):
            return JSONResponse({"errore": T["troppe"]}, 429)
        if not tetto.consuma():
            return JSONResponse({"errore": T["tetto"], "tetto": True}, 503)
        try:
            return rispondi(grafo, ricercatori, corpo.model_dump())
        except Exception:  # noqa: BLE001 — nessun dettaglio interno al visitatore
            log.exception("Errore durante la risposta")
            return JSONResponse({"errore": T["irraggiungibile"]}, 502)

    return app


app = crea_app()
