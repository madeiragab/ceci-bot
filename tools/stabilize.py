"""Tira "teleportes" dentro das animações: o alinhamento pelos pés faz o corpo pular de lado quando ela
agacha/abre a perna/senta. Aqui cada quadro anda em x para a cabeça ficar no mesmo lugar da folha
(medida em assets/faces.json). Grava fdx por quadro em consistency_targets.json; rodar extract.py depois.

Uso: python -I tools/stabilize.py
"""
import json
import os

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
A = os.path.join(ROOT, "assets")
# folhas em que ela se desloca de verdade (ou deita): não travar a cabeça
MOVES = {"1", "5", "6", "14", "21", "53", "55"}
MIN_SCORE, CAP = 0.65, 60


def main():
    meta = json.load(open(os.path.join(A, "frames.json"), encoding="utf8"))
    faces = json.load(open(os.path.join(A, "faces.json"), encoding="utf8"))
    tp = os.path.join(A, "consistency_targets.json")
    tg = json.load(open(tp, encoding="utf8"))
    report = {}
    for sid in meta:
        t = tg.setdefault(sid, {})
        old = {int(k): v for k, v in t.get("fdx", {}).items()}
        if sid in MOVES or sid not in faces:
            t.pop("fdx", None)
            continue
        rows = faces[sid]
        good = [k for k, r in enumerate(rows) if r["score"] >= MIN_SCORE]
        if len(good) < 2:
            continue
        sm = np.median([rows[k]["scale"] for k in good])
        good = [k for k in good if abs(rows[k]["scale"] / sm - 1) < 0.15]  # escala estranha = rosto falso
        if len(good) < 2:
            continue
        cx = np.median([rows[k]["cx"] for k in good])
        fdx = {}
        for k in good:
            # faces.json foi medido com o fdx antigo já aplicado: acumula
            d = old.get(k, 0) + float(np.clip(cx - rows[k]["cx"], -CAP, CAP))
            if abs(d) >= 3:
                fdx[str(k)] = round(d)
        for k, v in old.items():  # quadros sem medida confiável mantêm o ajuste anterior
            if k not in good and abs(v) >= 3:
                fdx[str(k)] = v
        if fdx:
            t["fdx"] = fdx
            report[sid] = max(abs(v) for v in fdx.values())
        else:
            t.pop("fdx", None)
    json.dump(tg, open(tp, "w"), indent=1)
    print("maior correção por folha (px):", dict(sorted(report.items(), key=lambda x: -x[1])))


if __name__ == "__main__":
    main()
