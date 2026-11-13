"""Impostazioni lette dalle variabili d'ambiente (mai chiavi scritte nel codice)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

RADICE = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Impostazioni:
    # "bedrock" in produzione (AWS); "finto" per i test e per provare senza AWS.
    modalita: str = field(default_factory=lambda: os.getenv("LUMEN_MODALITA", "bedrock"))
    regione: str = field(default_factory=lambda: os.getenv("AWS_REGION", "eu-central-1"))
    # Profilo europeo di Claude Haiku 4.5 su Bedrock: i dati restano nelle regioni UE.
    modello: str = field(default_factory=lambda: os.getenv("LUMEN_MODELLO", "eu.anthropic.claude-haiku-4-5-20251001-v1:0"))
    modello_riserva: str = field(default_factory=lambda: os.getenv("LUMEN_MODELLO_RISERVA", "eu.amazon.nova-lite-v1:0"))
    modello_embeddings: str = field(default_factory=lambda: os.getenv("LUMEN_EMBEDDINGS", "amazon.titan-embed-text-v2:0"))
    dimensioni_embeddings: int = field(default_factory=lambda: int(os.getenv("LUMEN_DIMENSIONI", "512")))
    # Documenti e indice: cartella locale oppure bucket S3 (s3://bucket/prefisso).
    cartella_documenti: str = field(default_factory=lambda: os.getenv("LUMEN_DOCUMENTI", str(RADICE / "documenti")))
    indice: str = field(default_factory=lambda: os.getenv("LUMEN_INDICE", str(RADICE / "indice")))
    # Tetto mensile di domande per tutta la demo (protegge la spesa) e limite per visitatore.
    tetto_mensile: int = field(default_factory=lambda: int(os.getenv("LUMEN_TETTO_MENSILE", "300")))
    tabella_contatori: str = field(default_factory=lambda: os.getenv("LUMEN_TABELLA", ""))
    domande_al_minuto: int = field(default_factory=lambda: int(os.getenv("LUMEN_DOMANDE_MINUTO", "8")))
    max_token_risposta: int = field(default_factory=lambda: int(os.getenv("LUMEN_MAX_TOKEN", "700")))
    origini_consentite: tuple[str, ...] = field(
        default_factory=lambda: tuple(
            o.strip() for o in os.getenv(
                "LUMEN_ORIGINI",
                "https://websolution-progetti.pages.dev,http://localhost:8000,http://127.0.0.1:8000",
            ).split(",") if o.strip()
        )
    )


def impostazioni() -> Impostazioni:
    return Impostazioni()
