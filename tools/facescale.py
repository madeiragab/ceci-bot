"""Mede o tamanho/posição do rosto (óculos + olhos) de cada quadro por template multi-escala.

Referência: rosto do idle (folha 22, quadro 0). Para cada folha, a escala do rosto
relativa à referência vira correção do "mult" em assets/consistency_targets.json.

Uso:
  python -I tools/facescale.py          # mede e grava assets/faces.json + relatório
  python -I tools/facescale.py --apply  # idem e corrige os mults (rodar extract.py depois)
"""
import json
import os
import sys

import numpy as np
from PIL import Image
from scipy.signal import fftconvolve

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
A = os.path.join(ROOT, "assets")
REF = (22, 0)
BOX = (33, 80, 102, 124)  # x0,y0,x1,y1 do rosto em s22/00 (sobrancelha até boca)
SCALES = np.exp(np.linspace(np.log(0.6), np.log(1.7), 56))
if "--multi" in sys.argv:
    SCALES = np.exp(np.linspace(np.log(0.72), np.log(1.4), 34))
MIN_SCORE = 0.55
NO_FACE = {"21"}  # saída (de costas / correndo para fora)
# rosto virado (3/4) engana o template: mede pela altura do corpo em pé vs o idle novo (folha: quadro)
BODY = {"3": 0}
BODY_REF = (57, 0)


def body_h(meta, sid, k):
    from scipy import ndimage as ndi
    f = meta[str(sid)]["frames"][k]
    a = np.asarray(Image.open(os.path.join(A, "sprites", f["file"])).convert("RGBA"))[..., 3] > 128
    lab, n = ndi.label(a)
    ys = np.where(lab == (np.argmax(ndi.sum(a, lab, range(1, n + 1))) + 1))[0]
    return float(ys.max() - ys.min())


def gray(path):
    im = np.asarray(Image.open(path).convert("RGBA"), dtype=np.float64) / 255
    a = im[..., 3:4]
    rgb = im[..., :3] * a + 0.5 * (1 - a)
    return rgb @ np.array([0.3, 0.59, 0.11]), im[..., 3]


def box_sum(x, h, w):
    c = np.pad(x, ((1, 0), (1, 0))).cumsum(0).cumsum(1)
    return c[h:, w:] - c[:-h, w:] - c[h:, :-w] + c[:-h, :-w]


def ncc(img, alpha, tpl):
    h, w = tpl.shape
    if img.shape[0] < h or img.shape[1] < w:
        return -1, (0, 0)
    t = tpl - tpl.mean()
    num = fftconvolve(img, t[::-1, ::-1], "valid")
    s1, s2 = box_sum(img, h, w), box_sum(img * img, h, w)
    var = s2 - s1 * s1 / t.size
    r = num / (np.sqrt(np.maximum(var, 1e-9)) * np.sqrt((t * t).sum()))
    # só onde há pele/óculos opacos e textura (fundo liso dá ruído numérico)
    r[(var / t.size < 0.004) | (box_sum(alpha, h, w) / t.size < 0.97)] = -1
    k = np.unravel_index(np.argmax(r), r.shape)
    return float(r[k]), k


def match(img, alpha, tpl_img):
    best = (-1, 1.0, (0, 0), tpl_img.size)
    for s in SCALES:
        w, h = max(8, round(tpl_img.width * s)), max(6, round(tpl_img.height * s))
        t = np.asarray(tpl_img.resize((w, h), Image.LANCZOS), np.float64)
        sc, pos = ncc(img, alpha, t)
        if sc > best[0]:
            best = (sc, float(s), pos, (w, h))
    return best


def templates(meta, faces, n=14):
    """Rostos de vários quadros já confiáveis (expressões diferentes) como modelos extras."""
    x0, y0, x1, y1 = BOX
    tw, th = x1 - x0, y1 - y0
    out = []
    for sid in sorted(faces, key=int):
        rows = faces[sid]
        for k, r in sorted(enumerate(rows), key=lambda kr: -kr[1]["score"])[:2]:
            if r["score"] < 0.8 or abs(r["scale"] - 1) > 0.06:
                continue
            f = meta[sid]["frames"][k]
            img, _ = gray(os.path.join(A, "sprites", f["file"]))
            w, h = tw * r["scale"], th * r["scale"]
            px, py = r["cx"] - f["ox"] - w / 2, r["cy"] - f["oy"] - h / 2
            crop = img[int(round(py)):int(round(py + h)), int(round(px)):int(round(px + w))]
            if crop.shape[0] > 10 and crop.shape[1] > 20:
                out.append((r["scale"], Image.fromarray(crop.astype(np.float32), mode="F")))
    step = max(1, len(out) // n)
    return out[::step][:n]


def main(apply=False):
    meta = json.load(open(os.path.join(A, "frames.json"), encoding="utf8"))
    ref, _ = gray(os.path.join(A, "sprites", meta[str(REF[0])]["frames"][REF[1]]["file"]))
    x0, y0, x1, y1 = BOX
    tpl = Image.fromarray(ref[y0:y1, x0:x1].astype(np.float32), mode="F")
    out, corr = {}, {}
    multi, only = "--multi" in sys.argv, "--apply-only" in sys.argv
    if only:
        old_faces = json.load(open(os.path.join(A, "faces.json")))
    elif multi:  # 2ª passada: só refaz folhas fracas, com vários modelos
        old_faces = json.load(open(os.path.join(A, "faces.json")))
        tpls = templates(meta, old_faces)
        print(len(tpls), "modelos", flush=True)
    for sid in sorted(meta, key=int):
        rows = []
        if only:  # --apply-only: usa as medidas já gravadas
            out[sid] = rows = old_faces[sid]
            best = max(r["score"] for r in rows)
            if sid not in NO_FACE and best >= 0.62:
                corr[sid] = float(np.median([r["scale"] for r in rows
                                             if r["score"] >= max(MIN_SCORE, best - 0.1)]))
            continue
        if multi and max(r["score"] for r in old_faces[sid]) >= 0.8:
            out[sid] = rows = old_faces[sid]
            best = max(r["score"] for r in rows)
            corr[sid] = float(np.median([r["scale"] for r in rows if r["score"] >= best - 0.1]))
            continue
        for f in meta[sid]["frames"]:
            img, alpha = gray(os.path.join(A, "sprites", f["file"]))
            cands = [(1.0, tpl)] + (tpls if multi else [])
            sc, s, (py, px), (w, h) = max(
                ((m[0], m[1] * ts, m[2], m[3]) for ts, t in cands for m in [match(img, alpha, t)]),
                key=lambda m: m[0])
            rows.append(dict(score=round(sc, 3), scale=round(s, 4),
                             cx=round(f["ox"] + px + w / 2, 1), cy=round(f["oy"] + py + h / 2, 1)))
        out[sid] = rows
        best = max(r["score"] for r in rows)
        good = [r["scale"] for r in rows if r["score"] >= max(MIN_SCORE, best - 0.1)]
        if sid not in NO_FACE and best >= 0.62:
            corr[sid] = float(np.median(good))
        print(sid, "ok %d/%d" % (len(good), len(rows)), "escala %.3f" % corr.get(sid, float("nan")),
              " ".join("%.2f@%.2f" % (r["scale"], r["score"]) for r in rows), flush=True)
    for sid, k in BODY.items():
        corr[sid] = body_h(meta, sid, k) / body_h(meta, *BODY_REF)
        print(sid, "pela altura do corpo: %.3f" % corr[sid])
    json.dump(out, open(os.path.join(A, "faces.json"), "w"), indent=0)
    v = np.array(list(corr.values()))
    print("rosto: min %.3f max %.3f desvio %.1f%%  sem rosto: %s" % (
        v.min(), v.max(), v.std() / v.mean() * 100, [s for s in meta if s not in corr]))
    if apply:
        tp = os.path.join(A, "consistency_targets.json")
        tg = json.load(open(tp, encoding="utf8")) if os.path.exists(tp) else {}
        applied = {s: meta[s].get("applied", {}).get("mult", 1.0) for s in meta}
        raw = {s: applied[s] / corr[s] for s in corr}  # mult que deixaria o rosto = referência
        k = 1 / float(np.median(list(raw.values())))  # mantém o tamanho médio
        for s in meta:
            t = tg.setdefault(s, {})
            if t.get("registered"):  # alinhada pelo desenho inteiro (tools/register.py)
                continue
            if s in raw:
                t["mult"] = round(raw[s] * k, 4)
            else:  # sem rosto visível: mantém a proporção corpo/idle de antes
                t["mult"] = round(applied[s] * raw[str(REF[0])] * k / applied[str(REF[0])], 4)
        json.dump(tg, open(tp, "w"), indent=1)
        print("mults gravados: min %.3f max %.3f" % (min(t["mult"] for t in tg.values()),
                                                     max(t["mult"] for t in tg.values())))


if __name__ == "__main__":
    main("--apply" in sys.argv or "--apply-only" in sys.argv)
