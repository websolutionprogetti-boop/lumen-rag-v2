"""Tabella prima/dopo dai file in risultati/ (creati da deploy/valuta_confronto.sh)."""
import json
from pathlib import Path

R = Path("risultati")
versioni = sorted({p.stem.split("-", 1)[1] for p in R.glob("valutazione-*.json")})
righe = {"domande di controllo superate": [], "lunghezza media (parole)": []}
metriche: dict[str, list] = {}
for v in versioni:
    val = json.loads((R / f"valutazione-{v}.json").read_text(encoding="utf-8"))
    righe["domande di controllo superate"].append(f"{sum(not c['errori'] for c in val)}/{len(val)}")
    righe["lunghezza media (parole)"].append(f"{sum(len(c['risposta'].split()) for c in val) / len(val):.0f}")
    f = R / f"ragas_risultati-{v}.json"
    medie = json.loads(f.read_text(encoding="utf-8"))["medie"] if f.exists() else {}
    for k, x in medie.items():
        metriche.setdefault(k, []).append(f"{x:.2f}")
    g = R / f"ragas_pertinenza_it-{v}.json"
    metriche.setdefault("answer_relevancy (giudice in italiano)", []).append(
        f"{json.loads(g.read_text(encoding='utf-8'))['media']:.2f}" if g.exists() else "-")
righe.update(metriche)
print("\n" + f"{'':40s}" + "".join(f"{v:>14s}" for v in versioni))
for nome, valori in righe.items():
    print(f"{nome:40s}" + "".join(f"{x:>14s}" for x in valori))
