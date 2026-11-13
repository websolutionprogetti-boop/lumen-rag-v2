"""RAGAS, passo 1: fa rispondere l'agente vero (Claude su Bedrock) a domande con risposta di riferimento
presa dai documenti dello studio e salva domanda, risposta, frammenti trovati e riferimento in ragas_dati.json.

Uso (CloudShell):  LUMEN_MODALITA=bedrock LUMEN_INDICE=s3://<bucket>/indice python scripts/ragas_dati.py
Costo: 12 domande, meno di un centesimo.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.agente import costruisci_grafo, rispondi  # noqa: E402
from app.config import impostazioni  # noqa: E402
from app.modelli import crea_modello  # noqa: E402
from app.ricerca import Indice, Ricercatore, crea_embeddings  # noqa: E402

# Riferimenti copiati dai documenti dello studio (documenti/documenti_*.json), senza aggiungere nulla.
DOMANDE = [
    ("it", "Siete aperti il sabato?",
     "Il sabato lo studio è aperto dalle 9:00 alle 13:00, solo su appuntamento."),
    ("it", "Quanto costa la pulizia dei denti?",
     "Igiene professionale (detartrasi e lucidatura): 70 euro. Igiene con sbiancamento delle macchie superficiali (air polishing): 90 euro."),
    ("it", "Quanto costa la prima visita?",
     "Prima visita con controllo completo: 50 euro. Se nella stessa seduta si esegue l'igiene professionale, la prima visita è gratuita."),
    ("it", "Cosa devo portare alla prima visita?",
     "Un documento d'identità, la tessera sanitaria, le radiografie recenti se ne hai (degli ultimi 2 anni) e l'elenco dei farmaci che prendi abitualmente."),
    ("it", "Entro quando devo disdire un appuntamento?",
     "Almeno 24 ore prima. Per un appuntamento del lunedì la disdetta va fatta entro il venerdì alle 18:30."),
    ("it", "Posso pagare a rate un impianto?",
     "Per le cure lunghe (ad esempio impianti o ortodonzia) è possibile pagare a rate senza interessi, concordando il piano di pagamento al momento del preventivo."),
    ("it", "Le spese dal dentista si possono detrarre?",
     "Le spese dentistiche danno diritto alla detrazione del 19% nella dichiarazione dei redditi, per la parte che supera la franchigia di 129,11 euro all'anno. Il pagamento deve essere tracciabile (bancomat, carta o bonifico): i pagamenti in contanti non sono detraibili."),
    ("it", "A che età devo portare mio figlio dal dentista?",
     "Intorno ai 3 anni di età, oppure prima se i genitori notano macchie o problemi sui denti da latte."),
    ("it", "Ogni quanto devo fare l'igiene?",
     "Per la maggior parte dei pazienti una seduta di igiene ogni 6 mesi. Il dentista può indicare una frequenza diversa in base alla situazione di ciascuno."),
    ("en", "Are you open on Saturday?",
     "On Saturdays the clinic is open from 9:00 am to 1:00 pm, by appointment only."),
    ("en", "How much is a first visit?",
     "First visit with a complete check-up: 50 euros. If professional teeth cleaning is done in the same session, the first visit is free."),
    ("en", "How often should I have my teeth cleaned?",
     "For most patients a cleaning session every 6 months. The dentist may suggest a different frequency depending on each person's situation."),
]


def main() -> None:
    imp = impostazioni()
    embeddings = crea_embeddings(imp)
    ricercatori = {l: Ricercatore(Indice.carica(imp.indice, l), embeddings) for l in ("it", "en")}
    grafo = costruisci_grafo(crea_modello(imp))
    righe = []
    for i, (lingua, domanda, riferimento) in enumerate(DOMANDE, start=1):
        esito = rispondi(grafo, ricercatori, {"domanda": domanda, "lingua": lingua})
        frammenti = [d.page_content for d in ricercatori[lingua].cerca(domanda, k=4)]  # gli stessi passati al modello
        righe.append({"user_input": domanda, "response": esito["risposta"], "retrieved_contexts": frammenti,
                      "reference": riferimento, "lingua": lingua})
        print(f"{i:2d}. {domanda}\n    -> {esito['risposta'][:140]}")
    Path("ragas_dati.json").write_text(json.dumps(righe, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{len(righe)} risposte salvate in ragas_dati.json")


if __name__ == "__main__":
    main()
