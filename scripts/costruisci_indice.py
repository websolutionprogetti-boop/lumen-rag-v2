"""Calcola gli embeddings dei documenti e salva l'indice (vettori .npy + frammenti .json).

Uso:
  python scripts/costruisci_indice.py                      # salva in ./indice
  LUMEN_INDICE=s3://bucket/indice python scripts/costruisci_indice.py   # salva su S3
Con LUMEN_MODALITA=finto usa embeddings finti (gratis, solo per prove).
"""
import logging
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(message)s")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import impostazioni  # noqa: E402
from app.documenti import carica_documenti, frammenta  # noqa: E402
from app.ricerca import Indice, crea_embeddings  # noqa: E402

imp = impostazioni()
embeddings = crea_embeddings(imp)
for lingua in ("it", "en"):
    frammenti = frammenta(carica_documenti(imp.cartella_documenti, lingua), lingua)
    indice = Indice.costruisci(frammenti, embeddings, lingua, pausa=0 if imp.modalita == "finto" else 0.6)
    indice.salva(imp.indice)
    print(f"{lingua}: {len(frammenti)} frammenti, vettori {indice.vettori.shape} -> {imp.indice}/{lingua}")
