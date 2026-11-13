"""L'agente come grafo LangGraph.

    START -> recupera -> modello --(chiede uno strumento?)--> strumenti -> modello -> ... -> END
                                   \\--(risposta pronta)--> END

- recupera: ricerca ibrida nei documenti e prepara il messaggio con i frammenti numerati;
- modello:  Claude Haiku su Bedrock, con le regole del prompt di sistema e lo strumento collegato;
- strumenti: esegue prenota_appuntamento (simulato) e restituisce il risultato al modello.
"""
from __future__ import annotations

import re
from typing import Annotated, TypedDict

from langchain_core.documents import Document
from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition

from .documenti import NOME_STUDIO, frammenta
from .privacy import oscura
from .prompt import NON_LO_SO, blocco_documenti, prompt_di_sistema
from .ricerca import Ricercatore
from .strumenti import STRUMENTI

LIMITI = {"domanda": 500, "storia": 6, "doc_visitatore": 3, "caratteri_doc_visitatore": 12_000, "giri_strumenti": 2}

RISPOSTA_SICURA = {
    "it": "Non posso valutare sintomi né dare indicazioni su farmaci o cure. Per un dolore, un gonfiore o un dente "
          "rotto contatta la segreteria dello studio. In caso di emergenza grave chiama il 112.",
    "en": "I can't assess symptoms or give advice on medicines or treatment. For pain, swelling or a broken tooth, "
          "contact the clinic's front desk. In a serious emergency, call 112.",
}


class Stato(TypedDict):
    lingua: str
    domanda: str
    precedente: str
    messaggi: Annotated[list[AnyMessage], add_messages]
    risultati: list[Document]
    ricercatore: Ricercatore


def costruisci_grafo(modello):
    def recupera(stato: Stato) -> dict:
        ricercatore = stato["ricercatore"]
        risultati = ricercatore.cerca(stato["domanda"], k=4)
        # Domanda di seguito ("e per i bambini?"): se trova poco, riprova insieme alla domanda precedente.
        if len(risultati) < 2 and stato["precedente"]:
            for d in ricercatore.cerca(stato["precedente"] + " " + stato["domanda"], k=4):
                if len(risultati) < 4 and all((d.metadata["doc_id"], d.metadata["n"]) !=
                                              (r.metadata["doc_id"], r.metadata["n"]) for r in risultati):
                    risultati.append(d)
        en = stato["lingua"] == "en"
        etichetta = "Question" if en else "Domanda"
        contenuto = f"{blocco_documenti(risultati, stato['lingua'])}\n\n{etichetta}: {stato['domanda']}"
        # Risposta breve a una domanda dell'assistente ("semplice", "martedì"): ricorda al modello la richiesta iniziale.
        if stato["precedente"] and len(stato["domanda"].split()) <= 3:
            contenuto += (f"\n(This is a short reply to your last question. The user's earlier request was: "
                          f"\"{stato['precedente']}\".)" if en else
                          f"\n(È una risposta breve alla tua ultima domanda. La richiesta precedente dell'utente era: "
                          f"\"{stato['precedente']}\".)")
        return {"risultati": risultati, "messaggi": [HumanMessage(content=contenuto)]}

    def chiama_modello(stato: Stato) -> dict:
        sistema = SystemMessage(content=prompt_di_sistema(NOME_STUDIO[stato["lingua"]], stato["lingua"]))
        # Dopo il numero massimo di giri con lo strumento, il modello deve rispondere senza usarlo.
        giri = sum(1 for m in stato["messaggi"] if isinstance(m, ToolMessage))
        risposta = modello.invoke([sistema, *stato["messaggi"]])
        if giri >= LIMITI["giri_strumenti"] and getattr(risposta, "tool_calls", None):
            risposta = AIMessage(content=RISPOSTA_SICURA[stato["lingua"]])
        return {"messaggi": [risposta]}

    grafo = StateGraph(Stato)
    grafo.add_node("recupera", recupera)
    grafo.add_node("modello", chiama_modello)
    grafo.add_node("strumenti", ToolNode(STRUMENTI, messages_key="messaggi"))
    grafo.add_edge(START, "recupera")
    grafo.add_edge("recupera", "modello")
    grafo.add_conditional_edges(
        "modello", lambda s: tools_condition(s, messages_key="messaggi"),
        {"tools": "strumenti", END: END})
    grafo.add_edge("strumenti", "modello")
    return grafo.compile()


# ---------------------------------------------------------------- uso dall'API


def _storia(storia, lingua: str) -> list[AnyMessage]:
    if not isinstance(storia, list):
        return []
    out: list[AnyMessage] = []
    for m in storia[-LIMITI["storia"]:]:
        if not isinstance(m, dict) or not isinstance(m.get("testo"), str):
            continue
        testo = oscura(m["testo"][:1500], lingua).testo
        if m.get("ruolo") == "utente":
            out.append(HumanMessage(content=testo))
        elif m.get("ruolo") == "assistente":
            out.append(AIMessage(content=testo))
    while out and not isinstance(out[0], HumanMessage):
        out.pop(0)
    # niente due messaggi di fila dello stesso tipo
    return [m for i, m in enumerate(out) if i == 0 or type(m) is not type(out[i - 1])]


def _documenti_visitatore(lista, lingua: str) -> list[Document]:
    if not isinstance(lista, list):
        return []
    docs = []
    for i, d in enumerate(lista[:LIMITI["doc_visitatore"]], start=1):
        if not isinstance(d, dict):
            continue
        testo = oscura(str(d.get("testo") or "")[:LIMITI["caratteri_doc_visitatore"]], lingua).testo
        if testo.strip():
            titolo = str(d.get("titolo") or (f"Uploaded document {i}" if lingua == "en" else f"Documento caricato {i}"))[:80]
            docs.append({"id": f"utente-{i}", "titolo": titolo, "testo": testo})
    return frammenta(docs, lingua, caricato_dal_visitatore=True)


def fonti_citate(risposta: str, risultati: list[Document]) -> list[dict]:
    usati = sorted({int(n) for n in re.findall(r"\[(\d{1,2})\]", risposta) if 1 <= int(n) <= len(risultati)})
    return [{"n": n, "docId": risultati[n - 1].metadata["doc_id"], "titolo": risultati[n - 1].metadata["titolo"],
             "utente": risultati[n - 1].metadata.get("utente", False), "estratto": risultati[n - 1].page_content}
            for n in usati]


_RESIDUI = ('{"tool_name"', '{"esito"', "<frammento", "</frammento")


def pulisci(testo: str) -> str:
    """Toglie dalla risposta i pezzi tecnici che il modello a volte ricopia (risultato grezzo dello
    strumento, tag dei frammenti) e una frase finale rimasta in sospeso con i due punti."""
    t = re.sub(r"</?(response|risposta|answer)>", "", testo)
    for residuo in _RESIDUI:
        k = t.find(residuo)
        if k >= 0:
            t = t[:k]
    t = t.rstrip()
    if t.endswith((":", ":.")):
        t = re.sub(r"\s*[^.!?\n]*:\.?$", "", t)
    return t.strip()


def _testo(messaggio) -> str:
    c = messaggio.content
    if isinstance(c, list):  # alcuni modelli restituiscono blocchi
        c = "".join(b.get("text", "") for b in c if isinstance(b, dict))
    return pulisci(str(c))


def rispondi(grafo, ricercatori: dict[str, Ricercatore], corpo: dict) -> dict:
    """Riceve lo stesso JSON della v1 ({domanda, lingua, storia, documenti}) e risponde nello stesso formato."""
    lingua = "en" if corpo.get("lingua") == "en" else "it"
    grezza = corpo.get("domanda").strip() if isinstance(corpo.get("domanda"), str) else ""
    if not grezza:
        raise ValueError("vuota")
    if len(grezza) > LIMITI["domanda"]:
        raise ValueError("lunga")
    domanda = oscura(grezza, lingua)
    storia = _storia(corpo.get("storia"), lingua)
    precedente = next((m.content for m in reversed(storia) if isinstance(m, HumanMessage)), "")
    ricercatore = ricercatori[lingua].con_documenti_visitatore(_documenti_visitatore(corpo.get("documenti"), lingua))

    finale = grafo.invoke({"lingua": lingua, "domanda": domanda.testo, "precedente": precedente,
                           "messaggi": storia, "risultati": [], "ricercatore": ricercatore},
                          {"recursion_limit": 10})
    risposta = _testo(finale["messaggi"][-1]) or RISPOSTA_SICURA[lingua]
    risultati = finale["risultati"]
    azioni = [{"strumento": m.name, "risultato": m.content} for m in finale["messaggi"] if isinstance(m, ToolMessage)]
    if azioni:  # la conferma viene dallo strumento, non dai documenti: niente citazioni
        risposta = re.sub(r"\s*\[\d{1,2}\]", "", risposta)
        codici = re.findall(r"DEMO-[0-9A-F]{6}", " ".join(str(a["risultato"]) for a in azioni))
        if codici and codici[-1] not in risposta:  # il codice deve sempre comparire nella conferma
            risposta += (f" Request code: {codici[-1]}." if lingua == "en" else f" Codice della richiesta: {codici[-1]}.")
    risposta = re.sub(r"\s*[^.!?\n]*:\s*\.(?=\s|$)", "", risposta)  # frase rimasta in sospeso ("...:.")
    return {
        "risposta": risposta,
        "nonLoSo": risposta.startswith(NON_LO_SO[lingua]),
        "fonti": fonti_citate(risposta, risultati),
        "oscurati": domanda.trovati,
        "azioni": azioni,
        "cercati": [{"n": i, "titolo": d.metadata["titolo"], "utente": d.metadata.get("utente", False),
                     "punteggio": d.metadata.get("punteggio")} for i, d in enumerate(risultati, start=1)],
    }
