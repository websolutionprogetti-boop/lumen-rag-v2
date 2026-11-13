"""Caricamento dei documenti dello studio e suddivisione in frammenti (un paragrafo = un frammento)."""
from __future__ import annotations

import json
import re
from pathlib import Path

from langchain_core.documents import Document

from .archivio import leggi_testo

NOME_STUDIO = {"it": "Studio Dentistico Lumen", "en": "Lumen Dental Clinic"}


def carica_documenti(cartella: str, lingua: str) -> list[dict]:
    """Legge documenti_<lingua>.json da una cartella locale o da S3 (s3://bucket/prefisso)."""
    dati = json.loads(leggi_testo(f"{cartella.rstrip('/')}/documenti_{lingua}.json"))
    return dati["documenti"]


def frammenta(documenti: list[dict], lingua: str, caricato_dal_visitatore: bool = False) -> list[Document]:
    frammenti: list[Document] = []
    for d in documenti:
        parti = [p.strip() for p in re.split(r"\n\s*\n", str(d["testo"])) if p.strip()]
        for i, testo in enumerate(parti, start=1):
            frammenti.append(Document(
                page_content=testo,
                metadata={
                    "doc_id": d["id"],
                    "titolo": d["titolo"],
                    "n": i,
                    "lingua": lingua,
                    "utente": caricato_dal_visitatore,
                },
            ))
    return frammenti


def carica_locale(lingua: str) -> list[dict]:
    """Scorciatoia per test e script: legge i documenti dalla cartella del progetto."""
    cartella = Path(__file__).resolve().parent.parent / "documenti"
    return carica_documenti(str(cartella), lingua)
