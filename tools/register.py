"""Alinha uma folha a um quadro de referência pelo desenho inteiro (escala + deslocamento x/y).

Busca a escala/posição do quadro `src` que mais coincide com `ref` (silhueta + luminância) e grava
na folha: mult (escala) e dx/dy (px finais) em consistency_targets.json. Rodar extract.py depois.

Uso: python -I tools/register.py 57:0 22:0
"""
import json
import os
import sys

import numpy as np
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
A = os.path.join(ROOT, "assets")
W, H, G = 400, 520, 500


def canvas(meta, sid, k, s=1.0, dx=0, dy=0):
    f = meta[str(sid)]["frames"][k]
    im = Image.open(os.path.join(A, "sprites", f["file"])).convert("RGBA")
    if s != 1.0:
        im = im.resize((max(1, round(im.width * s)), max(1, round(im.height * s))), Image.LANCZOS)
    c = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    c.alpha_composite(im, (int(W / 2 + f["ox"] * s + dx), int(G + f["oy"] * s + dy)))
    a = np.asarray(c, np.float32) / 255
    g = (a[..., :3] @ np.array([0.3, 0.59, 0.11])) * a[..., 3]
    return a[..., 3], g


def score(r, c):
    (ra, rg), (ca, cg) = r, c
    iou = np.minimum(ra, ca).sum() / max(1e-6, np.maximum(ra, ca).sum())
    m = (ra > 0.5) & (ca > 0.5)
    corr = np.corrcoef(rg[m], cg[m])[0, 1] if m.sum() > 100 else 0
    return iou + 0.5 * corr


def main(src, ref):
    meta = json.load(open(os.path.join(A, "frames.json"), encoding="utf8"))
    (ss, sk), (rs, rk) = [tuple(map(int, x.split(":"))) for x in (src, ref)]
    r = canvas(meta, rs, rk)
    best = (-9, 1.0, 0, 0)
    for s in np.arange(0.86, 1.15, 0.02):  # grosso, depois fino em volta do melhor
        for dx in range(-30, 31, 4):
            for dy in range(-30, 31, 4):
                v = score(r, canvas(meta, ss, sk, s, dx, dy))
                if v > best[0]:
                    best = (v, s, dx, dy)
    _, s0, x0, y0 = best
    for s in np.arange(s0 - 0.02, s0 + 0.021, 0.005):
        for dx in range(x0 - 4, x0 + 5):
            for dy in range(y0 - 4, y0 + 5):
                v = score(r, canvas(meta, ss, sk, s, dx, dy))
                if v > best[0]:
                    best = (v, s, dx, dy)
    v, s, dx, dy = best
    print("melhor: escala %.3f dx %+d dy %+d (nota %.3f; sem ajuste %.3f)" % (
        s, dx, dy, v, score(r, canvas(meta, ss, sk))))
    tp = os.path.join(A, "consistency_targets.json")
    tg = json.load(open(tp, encoding="utf8"))
    t = tg.setdefault(str(ss), {})
    applied = meta[str(ss)].get("applied", {})
    t["mult"] = round(applied.get("mult", 1.0) * s, 4)
    t["dx"] = round(applied.get("dx", 0) * s + dx)
    t["dy"] = round(applied.get("dy", 0) * s + dy)
    t["registered"] = "%d:%d" % (rs, rk)  # facescale não mexe na escala desta folha
    json.dump(tg, open(tp, "w"), indent=1)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
