"""Verifica TODAS as passagens de quadro do manifesto (entrada, passo a passo, volta do miolo, saída)
pelo rosto medido em assets/faces.json e aponta saltos de posição/tamanho ("teleporte").

Uso:
  python -I tools/transitions.py          # relatório
  python -I tools/transitions.py --apply  # grava deslocamento x por folha em consistency_targets.json
"""
import json
import os
import sys
from collections import defaultdict

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
A = os.path.join(ROOT, "assets")
IDLE = (57, 0)
OK = 0.75       # score mínimo do rosto para confiar na medida
JUMP = 10       # px de sprite (~5 px na tela no tamanho padrão)


def pairs(anims):
    for aid, a in anims.items():
        seq = [tuple(s[:2]) for s in a["seq"] if s[0]]
        if not seq:
            continue
        if aid != "idle":
            yield aid, "entrada", IDLE, seq[0]
        for x, y in zip(seq, seq[1:]):
            yield aid, "passo", x, y
        if a.get("loop"):
            i, j = a["loop"]
            yield aid, "miolo", tuple(a["seq"][j][:2]), tuple(a["seq"][i][:2])
        nxt = a.get("next", "idle")
        if nxt and nxt in anims and nxt != aid:
            yield aid, "saida", seq[-1], tuple(anims[nxt]["seq"][0][:2])


def main(apply=False):
    anims = json.load(open(os.path.join(A, "animations.json"), encoding="utf8"))
    faces = json.load(open(os.path.join(A, "faces.json"), encoding="utf8"))

    def face(sf):
        rows = faces.get(str(sf[0]), [])
        r = rows[sf[1]] if sf[1] < len(rows) else None
        return r if r and r["score"] >= OK else None

    bad, shift = [], defaultdict(list)
    n = 0
    for aid, kind, x, y in pairs(anims):
        fx, fy = face(x), face(y)
        if not (fx and fy):
            continue
        n += 1
        dx, dy = fy["cx"] - fx["cx"], fy["cy"] - fx["cy"]
        ds = fy["scale"] / fx["scale"] - 1
        cross = x[0] != y[0]
        if cross and IDLE[0] in (x[0], y[0]) and abs(dy) < JUMP:  # mesma altura de cabeça = mesma pose
            # quanto a folha "nova" deve andar para o rosto coincidir com o da folha conhecida
            other = y if x[0] == IDLE[0] else x
            sign = -1 if other is y else 1
            shift[other[0]].append(sign * dx)
        if abs(dx) > JUMP or abs(dy) > JUMP or abs(ds) > 0.06:
            bad.append((aid, kind, x, y, dx, dy, ds, cross))
    print("passagens medidas:", n)
    for aid, kind, x, y, dx, dy, ds, cross in sorted(bad, key=lambda b: -abs(b[4]) - abs(b[5])):
        print("%-16s %-7s %s->%s  dx %+5.0f dy %+5.0f esc %+4.0f%% %s" % (
            aid, kind, x, y, dx, dy, ds * 100, "ENTRE FOLHAS" if cross else ""))
    fix = {s: float(np.median(v)) for s, v in shift.items() if s != IDLE[0] and abs(np.median(v)) >= 3}
    print("deslocamento x sugerido por folha:", {s: round(v) for s, v in sorted(fix.items())})
    if apply and fix:
        tp = os.path.join(A, "consistency_targets.json")
        tg = json.load(open(tp, encoding="utf8"))
        for s, v in fix.items():
            t = tg.setdefault(str(s), {})
            t["dx"] = round(t.get("dx", 0) + v)
        json.dump(tg, open(tp, "w"), indent=1)
        print("gravado; rode tools/extract.py", " ".join(str(s) for s in sorted(fix)))


if __name__ == "__main__":
    main("--apply" in sys.argv)
