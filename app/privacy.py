"""Oscuramento dei dati personali prima che il testo arrivi al modello (stesse regole della v1)."""
from __future__ import annotations

import re
from dataclasses import dataclass

# (tipo in italiano, tipo in inglese, espressione regolare, sostituto IT, sostituto EN)
_REGOLE = [
    ("email", "email", re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I), "[email oscurata]", "[email masked]"),
    ("IBAN", "IBAN", re.compile(r"\bIT\s?\d{2}\s?[A-Z]\s?(?:[A-Z0-9]\s?){22}\b", re.I), "[IBAN oscurato]", "[IBAN masked]"),
    ("codice fiscale", "tax code", re.compile(r"\b[A-Z]{6}\s?\d{2}[A-EHLMPR-T]\d{2}[A-Z]\d{3}[A-Z]\b", re.I),
     "[codice fiscale oscurato]", "[tax code masked]"),
    ("numero di carta", "card number", re.compile(r"\b\d(?:[ -]?\d){12,18}\b"), "[numero oscurato]", "[number masked]"),
    ("telefono", "phone number",
     re.compile(r"(?:\+|00)\s?\d{2}[\s.-]?\d{2,4}(?:[\s.-]?\d{2,4}){2,3}\b|\b3\d{2}[\s.-]?\d{3}[\s.-]?\d{3,4}\b|\b0\d{1,3}[\s.-]?\d{5,8}\b"),
     "[telefono oscurato]", "[phone masked]"),
    ("data di nascita", "date of birth",
     re.compile(r"\b(?:nat[oa]|nascita|born|birth)\D{0,12}\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}\b", re.I),
     "[data di nascita oscurata]", "[date of birth masked]"),
]

# Recapiti dello studio fittizio: compaiono nei documenti ufficiali e non vanno oscurati.
_NON_OSCURARE = ["045 000 0000", "info@studiolumen.example", "privacy@studiolumen.example"]


@dataclass
class Oscurato:
    testo: str
    trovati: list[str]


def oscura(testo: str | None, lingua: str = "it") -> Oscurato:
    en = lingua == "en"
    out = str(testo or "")
    protetti = []
    for i, s in enumerate(_NON_OSCURARE):
        if s in out:
            out = out.replace(s, f"\x00{i}\x00")
            protetti.append(i)
    trovati: list[str] = []
    for tipo_it, tipo_en, regola, sost_it, sost_en in _REGOLE:
        out, n = regola.subn(sost_en if en else sost_it, out)
        if n:
            tipo = tipo_en if en else tipo_it
            if tipo not in trovati:
                trovati.append(tipo)
    for i in protetti:
        out = out.replace(f"\x00{i}\x00", _NON_OSCURARE[i])
    return Oscurato(out, trovati)
