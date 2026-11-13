"""Strumenti che l'agente può usare. Per ora uno solo, simulato: non prenota nulla e non salva dati."""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Literal

from langchain_core.tools import tool

TIPI_VISITA = ("prima visita", "igiene professionale", "controllo", "visita bambini", "visita ortodontica", "altro")


@tool
def prenota_appuntamento(
    tipo_visita: str,
    giorno_preferito: str,
    fascia_oraria: Literal["mattina", "pomeriggio"],
) -> dict:
    """Registra una richiesta di appuntamento SIMULATA per la demo (non prenota davvero, non salva nulla).

    Args:
        tipo_visita: tipo di visita con le parole dell'utente, ad esempio "prima visita", "igiene professionale",
            "visita bambini". Non serve scegliere varianti o prezzi: basta il tipo generico.
        giorno_preferito: giorno preferito indicato dall'utente, ad esempio "martedì" o "15 dicembre".
        fascia_oraria: "mattina" oppure "pomeriggio".
    """
    tipo = tipo_visita.strip().lower()[:60] or "altro"
    giorno = giorno_preferito.strip()[:40]
    if not giorno:
        return {"esito": "dati mancanti", "manca": "giorno_preferito"}
    istante = datetime.now(timezone.utc).isoformat()
    codice = "DEMO-" + hashlib.sha256(f"{tipo}|{giorno}|{fascia_oraria}|{istante}".encode()).hexdigest()[:6].upper()
    return {
        "esito": "richiesta simulata registrata",
        "codice": codice,
        "riepilogo": {"tipo_visita": tipo, "giorno_preferito": giorno, "fascia_oraria": fascia_oraria},
        "nota": "Demo: nessun appuntamento è stato prenotato e nessun dato è stato salvato. "
                "In uno studio vero la segreteria confermerebbe data e ora.",
    }


STRUMENTI = [prenota_appuntamento]
