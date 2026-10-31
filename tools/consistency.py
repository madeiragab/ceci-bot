"""Mede, por quadro, a largura do rosto e as cores (pele / mecha vermelha) da Ceci.

Uso: python tools/consistency.py  -> grava assets/consistency.json e imprime desvios por sheet.
Base para a padronização entre sheets em tools/extract.py (escala pela cabeça + correção de cor).
"""
import json
import os

import numpy as np
from PIL import Image
from scipy import ndimage as ndi

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPR = os.path.join(ROOT, "assets", "sprites")


def rgb2lab(rgb):
    c = rgb / 255.0
    c = np.where(c > 0.04045, ((c + 0.055) / 1.055) ** 2.4, c / 12.92)
    m = np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]])
    xyz = c @ m.T / np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], -1)


def masks(a):
    r, g, b, al = (a[..., i].astype(float) for i in range(4))
    op = al > 200
    skin = op & (r > 165) & (g > 105) & (b > 70) & (r > g) & (g > b) & (r - b > 35) & (r - g < 95)
    red = op & (r > 120) & (g < 0.45 * r) & (b < 0.55 * r)
    return op, skin, red


def face(a):
    """Blob do rosto (pele fechada sobre óculos/mechas) na metade superior; devolve (largura, máscara)."""
    op, skin, _ = masks(a)
    h = a.shape[0]
    rows = np.where(op.any(1))[0]
    top = rows.min()
    sk = skin.copy()
    sk[int(top + (h - top) * 0.5):] = False
    sk = ndi.binary_closing(sk, iterations=4)
    lab, n = ndi.label(sk)
    if not n:
        return None, None
    sizes = ndi.sum(sk, lab, range(1, n + 1))
    blob = lab == int(np.argmax(sizes)) + 1
    if sizes.max() < 400:
        return None, None
    widths = blob.sum(1)
    widths = widths[widths > 0]
    return float(np.percentile(widths, 85)), blob


def glasses_w(a, blob):
    """Largura da armação dos óculos (preto, colado na pele) — medida de cabeça que a franja não esconde."""
    if blob is None:
        return None
    op, skin, _ = masks(a)
    lab = rgb2lab(a[..., :3].astype(float))
    chroma = np.hypot(lab[..., 1], lab[..., 2])
    g = op & (lab[..., 0] < 14) & (chroma < 14) & ndi.binary_dilation(skin, iterations=3)
    ys, xs = np.where(blob)
    y0, y1, x0, x1 = ys.min(), ys.max(), xs.min(), xs.max()
    w = x1 - x0
    reg = np.zeros_like(g)
    reg[y0:int(y0 + (y1 - y0) * 0.8), max(0, int(x0 - 0.4 * w)):int(x1 + 0.4 * w)] = True
    g &= reg
    rows = g.sum(1)
    if rows.max() < 3:
        return None
    pk = int(np.argmax(ndi.uniform_filter1d(rows.astype(float), 9)))
    band = g[max(0, pk - int(0.3 * w)):pk + int(0.3 * w)]
    gx = np.where(band)[1]
    if len(gx) < 40:
        return None
    return float(np.percentile(gx, 98) - np.percentile(gx, 2))


def measure(path):
    a = np.asarray(Image.open(path).convert("RGBA"))
    fw, blob = face(a)
    op, skin, red = masks(a)
    lab = rgb2lab(a[..., :3].astype(float))
    out = dict(face_w=fw, glasses_w=glasses_w(a, blob))
    if blob is not None:
        s = blob & skin
        out["skin"] = [round(float(v), 2) for v in lab[s].mean(0)] if s.sum() > 50 else None
    if red.sum() > 50:
        out["red"] = [round(float(v), 2) for v in lab[red].mean(0)]
    dark = op & (lab[..., 0] < 40)
    if dark.sum() > 200:  # roupa/cabelo escuros: denuncia véu rosado e preto "lavado"
        out["dark"] = [round(float(v), 2) for v in lab[dark].mean(0)]
    # roupa (calça/jaqueta): tons médios marrom/cinza da metade de baixo, fora de pele e mechas
    h = a.shape[0]
    chroma = np.hypot(lab[..., 1], lab[..., 2])
    cloth = op & ~skin & ~red & (lab[..., 0] > 14) & (lab[..., 0] < 70) & (chroma < 26)
    cloth[:int(h * 0.5)] = False
    cloth[int(h * 0.9):] = False
    if cloth.sum() > 200:
        out["cloth"] = [round(float(v), 2) for v in lab[cloth].mean(0)]
    return out


def main():
    meta = json.load(open(os.path.join(ROOT, "assets", "frames.json")))
    res = {}
    for sid, v in sorted(meta.items(), key=lambda x: int(x[0])):
        res[sid] = [measure(os.path.join(SPR, f["file"])) if f else None for f in v["frames"]]
    json.dump(res, open(os.path.join(ROOT, "assets", "consistency.json"), "w"), indent=0)
    ref = res["22"]
    rfw = np.median([m["face_w"] for m in ref if m and m["face_w"]])
    rsk = np.median([m["skin"] for m in ref if m and m.get("skin")], 0)
    rrd = np.median([m["red"] for m in ref if m and m.get("red")], 0)
    print(f"ref 22: rosto {rfw:.1f}px pele Lab {np.round(rsk, 1)} mecha Lab {np.round(rrd, 1)}")
    for sid, ms in res.items():
        fws = [m["face_w"] for m in ms if m and m["face_w"]]
        sk = [m["skin"] for m in ms if m and m.get("skin")]
        rd = [m["red"] for m in ms if m and m.get("red")]
        fw = np.median(fws) if fws else float("nan")
        dsk = np.round(np.median(sk, 0) - rsk, 1) if sk else None
        drd = np.round(np.median(rd, 0) - rrd, 1) if rd else None
        spread = (max(fws) / min(fws)) if len(fws) > 1 else 1
        print(f"{sid:>2} rosto x{fw / rfw:.2f} (variação interna {spread:.2f})  dPele {dsk}  dMecha {drd}")




def lab2rgb(lab):
    L, A, B = lab[..., 0], lab[..., 1], lab[..., 2]
    fy = (L + 16) / 116
    f = np.stack([fy + A / 500, fy, fy - B / 200], -1)
    xyz = np.where(f > 0.2069, f ** 3, (f - 16 / 116) / 7.787) * np.array([0.95047, 1.0, 1.08883])
    m = np.array([[3.2406, -1.5372, -0.4986], [-0.9689, 1.8758, 0.0415], [0.0557, -0.2040, 1.0570]])
    c = xyz @ m.T
    c = np.where(c > 0.0031308, 1.055 * np.clip(c, 0, None) ** (1 / 2.4) - 0.055, 12.92 * c)
    return np.clip(c * 255, 0, 255)


def correct_colors(rgb, alpha, t):
    """Aplica a correção de pele/mecha de um sheet (pesos suaves por proximidade de cor em Lab)."""
    m = alpha > 0
    if not m.any() or not (t.get("skin_src") or t.get("ddark") or t.get("cloth_src")):
        return rgb
    lab = rgb2lab(rgb[m])
    out = lab.copy()
    if t.get("ddark"):
        w = np.clip((50 - lab[:, 0]) / 30, 0, 1)[:, None]
        out += w * np.array(t["ddark"])
    for k, sig in (("skin", 14.0), ("red", 18.0), ("cloth", 16.0)):
        src, d = t.get(f"{k}_src"), t.get(f"d{k}")
        if src is None or d is None:
            continue
        dist2 = ((lab - np.array(src)) ** 2).sum(1)
        w = np.exp(-dist2 / (2 * sig * sig))[:, None]
        out += w * np.array(d)
    rgb = rgb.copy()
    rgb[m] = lab2rgb(out)
    return rgb


# Quadros de frente, olhos abertos, sem mão no rosto (revisão visual). Padrão: primeiro e último.
# Sheets sem pose neutra de frente usam só a altura do corpo (escala mediana).
REF_FRAMES = {"6": [6], "9": [0, 1, 5], "10": [0], "11": [0], "12": [0, 3], "13": [0], "16": [0, 2, 3, 4],
              "20": [3], "29": [0, 8], "33": [0], "34": [0], "38": [0], "39": [0], "40": [0], "41": [0],
              "43": [0], "44": [0], "45": [0], "46": [0], "47": [0, 1, 2, 3, 4, 5], "51": [0, 8], "53": [7],
              "54": [0], "55": [0]}
NO_HEAD_SCALE = {"3", "5", "8", "14", "15", "17", "21"}  # cabeça virada/perfil/mãos no rosto em todos
HEAD_WEIGHT = 0.9  # 1 = cabeça idêntica (corpo varia), 0 = só altura do corpo


def make_targets():
    """Calcula multiplicador de escala e deltas de cor por sheet rumo à 'Ceci mediana'."""
    res = json.load(open(os.path.join(ROOT, "assets", "consistency.json")))
    tpath = os.path.join(ROOT, "assets", "consistency_targets.json")
    frames = json.load(open(os.path.join(ROOT, "assets", "frames.json")))
    old = {k: v.get("applied", {}) for k, v in frames.items()}  # o que a última extração aplicou de fato
    fw, sk, rd, dk = {}, {}, {}, {}
    for sid, ms in res.items():
        o = old.get(sid, {})
        mult = o.get("mult", 1.0)
        refs = REF_FRAMES.get(sid, [0, len(ms) - 1])
        f = [ms[k]["glasses_w"] / mult for k in refs
             if 0 <= k < len(ms) and ms[k] and ms[k].get("glasses_w")]  # sem o ajuste anterior
        allv = [m["glasses_w"] / mult for m in ms if m and m.get("glasses_w")]
        if allv:  # mediana robusta de todos os quadros: protege contra falha de medida na pose neutra
            # falhas de medida (olho fechado, rosto coberto) sempre dão valores baixos: ancora no 75º percentil
            md = np.percentile(allv, 75)
            robust = float(np.median([v for v in allv if 0.8 * md <= v <= 1.25 * md] or allv))
            ref = float(np.median(f)) if f else robust
            fw[sid] = ref if abs(ref / robust - 1) < 0.12 else robust
        s = [m["skin"] for m in ms if m and m.get("skin")]
        r = [m["red"] for m in ms if m and m.get("red")]
        if s:
            sk[sid] = np.median(s, 0) - np.array(o.get("dskin", [0, 0, 0]))
        if r:
            rd[sid] = np.median(r, 0) - np.array(o.get("dred", [0, 0, 0]))
        d = [m["dark"] for m in ms if m and m.get("dark")]
        if d:
            dk[sid] = np.median(d, 0) - np.array(o.get("ddark", [0, 0, 0])) * 0.8  # peso médio na faixa escura
    tf = float(np.median([v for k, v in fw.items() if k not in NO_HEAD_SCALE]))
    ts, tr = np.median(list(sk.values()), 0), np.median(list(rd.values()), 0)
    td = np.median(list(dk.values()), 0)
    mults = {k: (tf / v) ** HEAD_WEIGHT for k, v in fw.items() if k not in NO_HEAD_SCALE}
    mmed = float(np.median(list(mults.values())))
    out = {}
    for sid in res:
        out[sid] = dict(mult=round(mults.get(sid, mmed), 4))
        if sid in sk:
            out[sid].update(skin_src=[round(float(x), 2) for x in sk[sid]],
                            dskin=[round(float(x), 2) for x in ts - sk[sid]])
        if sid in dk:
            out[sid]["ddark"] = [round(float(x), 2) for x in td - dk[sid]]
        if sid in rd:
            out[sid].update(red_src=[round(float(x), 2) for x in rd[sid]],
                            dred=[round(float(x), 2) for x in tr - rd[sid]])
    json.dump(out, open(tpath, "w"), indent=1)
    print("alvos gravados; escala min/max", min(v["mult"] for v in out.values()),
          max(v["mult"] for v in out.values()))


if __name__ == "__main__":
    import sys
    main()
    if "--targets" in sys.argv:
        make_targets()
