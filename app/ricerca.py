"""Ricerca ibrida: semantica (embeddings + FAISS) e per parole chiave (BM25), unite con la Reciprocal Rank Fusion.

- La ricerca semantica trova i frammenti con lo stesso significato anche se usano parole diverse
  ("quanto si paga la pulizia?" -> "Igiene professionale: 70 euro").
- BM25 premia le parole esatte (numeri, nomi, sigle) dove gli embeddings a volte sbagliano.
- La v1 usava solo BM25: la v2 li combina.

L'indice si costruisce una volta (scripts/costruisci_indice.py) e si salva come vettori .npy + JSON:
niente pickle, quindi caricarlo da S3 non esegue codice.
"""
from __future__ import annotations

import hashlib
import io
import json
import logging
import time
import re
import unicodedata
from dataclasses import dataclass

import numpy as np
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from rank_bm25 import BM25Okapi

from .archivio import leggi_bytes, scrivi_bytes
from .config import Impostazioni

try:  # FAISS in locale e nell'immagine Docker; nel pacchetto zip di Lambda non entra (limite di 250 MB)
    import faiss
except ImportError:  # pragma: no cover
    faiss = None


class IndiceVettoriale:
    """Ricerca esatta per somiglianza coseno: FAISS (IndexFlatIP) se installato, altrimenti NumPy.

    Con poche decine di frammenti i due danno gli stessi risultati; FAISS serve quando i documenti crescono.
    """

    def __init__(self, vettori: np.ndarray):
        self.vettori = np.ascontiguousarray(vettori, dtype=np.float32)
        self.motore = "faiss" if faiss is not None else "numpy"
        if faiss is not None:
            self._faiss = faiss.IndexFlatIP(self.vettori.shape[1])
            self._faiss.add(self.vettori)

    def cerca(self, query: np.ndarray, n: int) -> list[tuple[int, float]]:
        q = np.ascontiguousarray(query.reshape(1, -1), dtype=np.float32)
        if faiss is not None:
            punteggi, posizioni = self._faiss.search(q, n)
            return [(int(i), float(s)) for s, i in zip(punteggi[0], posizioni[0]) if i >= 0]
        somiglianze = self.vettori @ q[0]
        ordine = np.argsort(-somiglianze, kind="stable")[:n]
        return [(int(i), float(somiglianze[i])) for i in ordine]


# ---------------------------------------------------------------- embeddings


class EmbeddingsFinti(Embeddings):
    """Embeddings deterministici (parole -> hash) per test e prove senza AWS. Non costano nulla."""

    def __init__(self, dimensioni: int = 256):
        self.dimensioni = dimensioni

    def _vettore(self, testo: str) -> list[float]:
        v = np.zeros(self.dimensioni, dtype=np.float32)
        for parola in parole(testo, "it"):
            h = int(hashlib.md5(parola.encode()).hexdigest(), 16)
            v[h % self.dimensioni] += 1.0
        norma = float(np.linalg.norm(v)) or 1.0
        return (v / norma).tolist()

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vettore(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vettore(text)


log = logging.getLogger("lumen")


def config_aws():
    """Ripetizioni automatiche con attesa crescente: gli account nuovi hanno limiti di richieste bassi."""
    from botocore.config import Config

    return Config(retries={"max_attempts": 10, "mode": "adaptive"}, connect_timeout=5, read_timeout=25)


def crea_embeddings(imp: Impostazioni) -> Embeddings:
    if imp.modalita == "finto":
        return EmbeddingsFinti()
    from langchain_aws import BedrockEmbeddings

    return BedrockEmbeddings(
        model_id=imp.modello_embeddings,
        region_name=imp.regione,
        model_kwargs={"dimensions": imp.dimensioni_embeddings, "normalize": True},
        config=config_aws(),
    )


# ---------------------------------------------------------------- parole chiave (per BM25)

_STOP_IT = set("""a ad al alla alle allo agli ai anche avere c che chi ci col come con cosa cui da dal dalla dalle dallo dagli
dai degli dei del della delle dello di dove e ed fa fare gli ha hanno ho i il in io la le li lo loro ma mi mio mia ne nei
nel nella nelle nello negli no noi non o per perche piu puo quale quali quando quanto quanti quanta quante quello questa
questo qui se si sia siete sono su sua sue sui sul sulla suo ti tra tu un una uno vi voi vostro vostra tuo tua essere stato
stata fate fanno posso potete devo dovete serve servono""".split())
_STOP_EN = set("""a an and are as at be been by can could do does did for from had has have how i if in into is it its me
my no not of on or our please so than that the their them then there these they this to too us was we what when where which
who why will with would you your""".split())

# Pochi sinonimi utili per BM25 (la parte semantica copre il resto).
_SINONIMI = {
    "costo": "prezzo", "costa": "prezzo", "costano": "prezzo", "tariffa": "prezzo", "quanto": "prezzo",
    "pulizia": "igiene", "tartaro": "igiene", "aperti": "aperto", "orario": "orari", "chiusi": "chiuso",
    "disdire": "disdetta", "annullare": "disdetta", "spostare": "disdetta", "bancomat": "pagare", "rate": "pagare",
    "bimbo": "bambini", "bambino": "bambini", "figlio": "bambini", "figlia": "bambini", "auto": "parcheggio",
    "macchina": "parcheggio", "730": "detrazione", "tasse": "detrazione", "carie": "otturazione",
    "cost": "price", "fee": "price", "cleaning": "hygiene", "cancel": "cancellation", "kid": "children",
    "kids": "children", "child": "children", "car": "parking", "tax": "deduction", "cavity": "filling",
}


def _radice(p: str, lingua: str) -> str:
    if len(p) <= 4:
        return p
    if lingua == "en":
        return re.sub(r"(ations|ation|ings|ing|ed|ies|es|ly|s)$", "", p) or p
    return re.sub(r"(zione|zioni|mente|ando|endo|ato|ata|ati|ate|ito|ita|iti|ite|are|ere|ire|i|e|o|a)$", "", p) or p


def parole(testo: str, lingua: str = "it") -> list[str]:
    t = unicodedata.normalize("NFD", str(testo).lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    t = re.sub(r"[^a-z0-9\s]", " ", t)
    stop = _STOP_EN if lingua == "en" else _STOP_IT
    out: list[str] = []
    for p in t.split():
        if p in stop:
            continue
        out.append(_radice(p, lingua))
        if p in _SINONIMI:
            out.append(_radice(_SINONIMI[p], lingua))
    return [p for p in out if len(p) > 1]


# ---------------------------------------------------------------- indice


def _chiave(d: Document) -> str:
    return f"{d.metadata['doc_id']}#{d.metadata['n']}"


@dataclass
class Indice:
    lingua: str
    frammenti: list[Document]
    vettori: np.ndarray  # una riga per frammento, normalizzata

    # ---- salvataggio senza pickle: vettori .npy + frammenti .json
    def salva(self, base: str) -> None:
        buf = io.BytesIO()
        np.save(buf, self.vettori.astype(np.float32))
        scrivi_bytes(f"{base.rstrip('/')}/{self.lingua}/vettori.npy", buf.getvalue())
        dati = [{"testo": d.page_content, "metadata": d.metadata} for d in self.frammenti]
        scrivi_bytes(f"{base.rstrip('/')}/{self.lingua}/frammenti.json", json.dumps(dati, ensure_ascii=False).encode())

    @classmethod
    def carica(cls, base: str, lingua: str) -> "Indice":
        vettori = np.load(io.BytesIO(leggi_bytes(f"{base.rstrip('/')}/{lingua}/vettori.npy")), allow_pickle=False)
        dati = json.loads(leggi_bytes(f"{base.rstrip('/')}/{lingua}/frammenti.json"))
        frammenti = [Document(page_content=x["testo"], metadata=x["metadata"]) for x in dati]
        return cls(lingua, frammenti, vettori)

    @classmethod
    def costruisci(cls, frammenti: list[Document], embeddings: Embeddings, lingua: str,
                   pausa: float = 0.0) -> "Indice":
        # Il titolo aiuta la ricerca semantica a capire di cosa parla il paragrafo.
        testi = [f"{d.metadata['titolo']}. {d.page_content}" for d in frammenti]
        vettori = []
        for i, testo in enumerate(testi, start=1):  # uno alla volta, con pausa: niente picchi di richieste
            vettori.append(embeddings.embed_query(testo))
            if pausa:
                time.sleep(pausa)
            if i % 10 == 0:
                log.info("%s: %d/%d frammenti", lingua, i, len(testi))
        return cls(lingua, frammenti, np.array(vettori, dtype=np.float32))


class Ricercatore:
    """Unisce ricerca semantica (coseno su vettori normalizzati) e BM25."""

    def __init__(self, indice: Indice, embeddings: Embeddings):
        self.lingua = indice.lingua
        self.embeddings = embeddings
        self.frammenti = list(indice.frammenti)
        self.vettori = np.ascontiguousarray(indice.vettori, dtype=np.float32)
        self.indice_vettoriale = IndiceVettoriale(self.vettori)
        self._parole = [parole(f"{d.metadata['titolo']} {d.page_content}", self.lingua) for d in self.frammenti]
        self.bm25 = BM25Okapi(self._parole)

    def con_documenti_visitatore(self, extra: list[Document]) -> "Ricercatore":
        """Copia del ricercatore che include anche i documenti caricati dal visitatore (solo per questa domanda)."""
        if not extra:
            return self
        testi = [f"{d.metadata['titolo']}. {d.page_content}" for d in extra]
        nuovi = np.array(self.embeddings.embed_documents(testi), dtype=np.float32)
        return Ricercatore(Indice(self.lingua, self.frammenti + extra, np.vstack([self.vettori, nuovi])), self.embeddings)

    def cerca(self, domanda: str, k: int = 4, soglia_semantica: float = 0.2, candidati: int = 8) -> list[Document]:
        if not domanda.strip():
            return []
        n = min(candidati, len(self.frammenti))
        # 1) semantica: somiglianza coseno, teniamo solo i frammenti abbastanza vicini
        try:
            q = np.array(self.embeddings.embed_query(domanda), dtype=np.float32)
            semantici = [i for i, s in self.indice_vettoriale.cerca(q, n) if s >= soglia_semantica]
        except Exception:  # noqa: BLE001 — se gli embeddings non rispondono, resta la ricerca per parole chiave
            log.exception("Ricerca semantica non disponibile, uso solo BM25")
            semantici = []
        # 2) parole chiave: BM25, solo frammenti con almeno una parola in comune con la domanda
        termini = parole(domanda, self.lingua)
        bm = self.bm25.get_scores(termini) if termini else np.zeros(len(self.frammenti))
        per_parole = [int(i) for i in np.argsort(-bm)[:n] if bm[i] > 0]
        # 3) Reciprocal Rank Fusion: conta la posizione in ciascuna classifica, non il punteggio grezzo
        punti: dict[int, float] = {}
        for classifica in (semantici, per_parole):
            for pos, i in enumerate(classifica):
                punti[i] = punti.get(i, 0.0) + 1.0 / (60 + pos + 1)
        migliori = sorted(punti, key=punti.get, reverse=True)[:k]
        return [Document(page_content=self.frammenti[i].page_content,
                         metadata={**self.frammenti[i].metadata, "punteggio": round(punti[i] * 1000, 2)})
                for i in migliori]


