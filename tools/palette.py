"""Paleta única: mede pele, mechas vermelhas, pretos e roupa em TODAS as folhas e ajusta os alvos de
cor de cada uma rumo à mediana geral (iterativo: rodar, extrair, rodar de novo refina).

Uso: python -I tools/palette.py            # mede e atualiza consistency_targets.json
     python -I tools/palette.py --report   # só mostra o quanto cada folha ainda difere
"""
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from consistency import measure  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
A = os.path.join(ROOT, "assets")
KEYS = {"skin": "dskin", "red": "dred", "dark": "ddark", "cloth": "dcloth"}
SKIP = set()  # folhas fora do ajuste (todas entram; a saída 21 também)
NO_CLASS = {("21", "cloth")}  # saída: metade dos quadros é só o livro/mão, a medida de roupa não vale


def main(report=False):
    meta = json.load(open(os.path.join(A, "frames.json"), encoding="utf8"))
    tp = os.path.join(A, "consistency_targets.json")
    tg = json.load(open(tp, encoding="utf8"))
    meas = {}
    only = [a for a in sys.argv[1:] if a.isdigit()]  # ex.: palette.py 21 → só ajusta a folha 21
    for sid in sorted(meta, key=int):
        ms = [measure(os.path.join(A, "sprites", f["file"])) for f in meta[sid]["frames"] if f]
        meas[sid] = {k: np.median([m[k] for m in ms if m.get(k) is not None], 0)
                     for k in KEYS if any(m.get(k) is not None for m in ms)}
    target = {k: np.median([m[k] for s, m in meas.items() if k in m and s not in SKIP], 0) for k in KEYS}
    print("alvo", {k: np.round(v, 1).tolist() for k, v in target.items()})
    worst = []
    for sid, m in meas.items():
        dev = {k: float(np.linalg.norm(m[k] - target[k])) for k in m}
        worst.append((max(dev.values()), sid, dev))
        if report or sid in SKIP or (only and sid not in only):
            continue
        t = tg.setdefault(sid, {})
        for k, dk in KEYS.items():
            if k not in m or (sid, k) in NO_CLASS:
                continue
            old = np.array(t.get(dk, [0, 0, 0]), float)
            if k != "dark":  # peso gaussiano em volta da cor ORIGINAL (antes da correção)
                t[k + "_src"] = [round(float(x), 2) for x in m[k] - old]
            t[dk] = [round(float(x), 2) for x in old + (target[k] - m[k])]
    for w, sid, dev in sorted(worst, reverse=True)[:8]:
        print("folha %s difere %.1f Lab  %s" % (sid, w, {k: round(v, 1) for k, v in dev.items()}))
    print("mediana das diferenças: %.1f Lab" % float(np.median([w[0] for w in worst])))
    if not report:
        json.dump(tg, open(tp, "w"), indent=1)


if __name__ == "__main__":
    main("--report" in sys.argv)
