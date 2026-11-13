"""Modelli linguistici: Claude Haiku su Bedrock (con riserva Amazon Nova) oppure un modello finto per i test."""
from __future__ import annotations

import re
from typing import Any

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from .config import Impostazioni
from .prompt import NON_LO_SO
from .strumenti import STRUMENTI


def crea_modello(imp: Impostazioni):
    """Restituisce il modello già collegato agli strumenti."""
    if imp.modalita == "finto":
        return ModelloFinto()
    from langchain_aws import ChatBedrockConverse

    from .ricerca import config_aws

    principale = ChatBedrockConverse(
        model=imp.modello, region_name=imp.regione, temperature=0, max_tokens=imp.max_token_risposta,
        config=config_aws())
    riserva = ChatBedrockConverse(
        model=imp.modello_riserva, region_name=imp.regione, temperature=0, max_tokens=imp.max_token_risposta,
        config=config_aws())
    # Se Claude non risponde (modello non disponibile, limite di richieste) si passa ad Amazon Nova.
    return principale.bind_tools(STRUMENTI).with_fallbacks([riserva.bind_tools(STRUMENTI)])


class ModelloFinto(BaseChatModel):
    """Modello deterministico per i test: imita il comportamento atteso senza chiamare AWS.

    - se l'utente chiede di prenotare e non è ancora stato usato lo strumento, chiama prenota_appuntamento;
    - se ha appena ricevuto il risultato dello strumento, riporta il codice;
    - altrimenti risponde con la prima frase del frammento 1, citandolo, oppure con "non lo so".
    """

    @property
    def _llm_type(self) -> str:
        return "finto"

    def bind_tools(self, tools: Any, **kwargs: Any) -> "ModelloFinto":  # noqa: ARG002
        return self

    def _generate(self, messages: list[BaseMessage], stop: list[str] | None = None,
                  run_manager: CallbackManagerForLLMRun | None = None, **kwargs: Any) -> ChatResult:
        ultimo = messages[-1]
        inglese = "front-desk assistant" in str(messages[0].content)
        if isinstance(ultimo, ToolMessage):
            codice = re.search(r"DEMO-[0-9A-F]{6}", str(ultimo.content))
            testo = (f"Request recorded: code {codice.group(0) if codice else '?'}. It's a demo: nothing was booked."
                     if inglese else
                     f"Richiesta registrata: codice {codice.group(0) if codice else '?'}. È una demo: non è stato prenotato nulla.")
            return ChatResult(generations=[ChatGeneration(message=AIMessage(content=testo))])
        domanda = str(ultimo.content).split("</documenti>")[-1].lower()
        if isinstance(ultimo, HumanMessage) and re.search(r"\bprenot|\bbook", domanda):
            chiamata = {"name": "prenota_appuntamento", "id": "chiamata-1",
                        "args": {"tipo_visita": "prima visita", "giorno_preferito": "martedì", "fascia_oraria": "mattina"}}
            return ChatResult(generations=[ChatGeneration(message=AIMessage(content="", tool_calls=[chiamata]))])
        frammento = re.search(r'<frammento numero="1"[^>]*>\n(.+?)(?:\.|\n)', str(ultimo.content), re.S)
        if frammento:
            testo = f"{frammento.group(1).strip()}. [1]"
        else:
            testo = NON_LO_SO["en" if inglese else "it"] + (" Please contact the front desk." if inglese else " Contatta la segreteria.")
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=testo))])
