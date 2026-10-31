"""Tamanho visual igual ao idle: compara a área do desenho (componente principal, sem efeitos soltos)
do 1º quadro de cada folha com o idle (57.0) e ajusta o mult. Folhas cujo 1º quadro não é a pose em pé
limpa (sentada, objetos, porta) recebem o fator mediano. Rodar extract.py depois.

Uso: python -I tools/sizematch.py
"""
import json
import os

import numpy as np
from PIL import Image
from scipy import ndimage as ndi

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
A = os.path.join(ROOT, "assets")
REF = ("57", 0)
# 1º quadro em pé (inclui as folhas antigas de cabeça grande, mesmo com rosto de lado)
STANDING = {"47", "49", "56", "2", "3", "4", "5", "7", "8", "9", "10", "11", "12", "13", "16", "17", "18",
            "19", "20"}
SKIP = {"1", "21", "57"}


def size(meta, sid, k):
    """(altura, raiz da área) do componente principal (sem efeitos soltos)."""
    f = meta[sid]["frames"][k]
    a = np.asarray(Image.open(os.path.join(A, "sprites", f["file"])).convert("RGBA"))[..., 3] > 128
    lab, n = ndi.label(a)
    big = lab == (int(np.argmax(ndi.sum(a, lab, range(1, n + 1)))) + 1)
    ys = np.where(big)[0]
    return float(ys.max() - ys.min()), float(np.sqrt(big.sum()))


def main():
    meta = json.load(open(os.path.join(A, "frames.json"), encoding="utf8"))
    faces = json.load(open(os.path.join(A, "faces.json"), encoding="utf8"))
    rh, ra = size(meta, *REF)
    fac = {}
    for sid in meta:
        if sid in SKIP:
            continue
        r = faces.get(sid, [{}])[0]
        if sid in STANDING or r.get("score", 0) >= 0.85:
            h, a = size(meta, sid, 0)
            fac[sid] = min(rh / h, ra / a)  # nunca maior que o idle, nem na altura nem na área
    med = float(np.median(list(fac.values())))
    tp = os.path.join(A, "consistency_targets.json")
    tg = json.load(open(tp, encoding="utf8"))
    for sid in meta:
        if sid in SKIP:
            continue
        f = float(np.clip(fac.get(sid, med), 0.8, 1.15))
        t = tg.setdefault(sid, {})
        t["mult"] = round(meta[sid].get("applied", {}).get("mult", 1.0) * f, 4)
        t["dx"] = round(meta[sid].get("applied", {}).get("dx", 0) * f)
        if t.get("fdx"):
            t["fdx"] = {k: round(v * f) for k, v in t["fdx"].items()}
    json.dump(tg, open(tp, "w"), indent=1)
    print("fator mediano %.3f; por folha:" % med, {s: round(v, 3) for s, v in sorted(fac.items(), key=lambda x: int(x[0]))})


if __name__ == "__main__":
    main()
