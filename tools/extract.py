"""Extrai os quadros das spritesheets (fundo magenta) para PNGs transparentes alinhados.

Uso: python tools/extract.py [ids...]
Gera assets/sprites/sNN/KK.png, assets/frames.json e _preview/aligned_NN.png.
Ajuste manual: em SHEETS, "cuts" (lista de x de corte no sheet original) substitui o corte automático,
"anchor" {quadro: [dx, dy]} soma um deslocamento (px finais) ao alinhamento de um quadro.
"""
import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage as ndi

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from consistency import correct_colors  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "assetsoriginal")
OUT = os.path.join(ROOT, "assets", "sprites")
STAND_H = 340  # altura da Ceci em pé nos PNGs preparados

# n = quadros reais; ref = quadro em pé usado p/ normalizar escala
SHEETS = {i: {"n": 8} for i in range(1, 58)}
FILES = {57: "idle.png"}  # folhas com nome próprio em assetsoriginal/
for i, n in {5: 10, 6: 7, 10: 7, 11: 5, 12: 5, 13: 6, 14: 7, 15: 6, 16: 7, 20: 6, 21: 8,
             43: 7, 44: 6, 45: 6, 46: 7, 47: 6, 51: 9, 29: 9, 41: 6}.items():
    SHEETS[i]["n"] = n
SHEETS[6]["ref"] = 6
SHEETS[53]["ref"] = 7
SHEETS[21]["ref"] = 0
SHEETS[56]["n"] = 4  # olhando para baixo (esq., centro, dir., dir.)
SHEETS[51]["align"] = "torso"  # sentada balançando as pernas: pernas não podem mover o corpo
# balanço (2-7): rosto travado no mesmo lugar (medido por tools/facescale.py); só as pernas se mexem
SHEETS[51]["anchor"] = {2: [-12, -10], 3: [10, 7], 4: [1, 0], 5: [-4, 10], 6: [14, -7], 7: [-1, 0]}
# sentada de verdade na beirada da barra de tarefas: o assento (fim das coxas, ~67 px acima dos pés) vai
# para a linha do chão e as pernas balançam por cima da barra (antes ela sentava no ar)
SIT_DROP = 67
SHEETS[51]["anchor"] = {k: [dx, dy + SIT_DROP] for k, (dx, dy) in SHEETS[51]["anchor"].items()}
SHEETS[5]["align"] = "torso"  # caminhada: pés abrem/fecham, o tronco é o ponto estável


def magentaness(a):
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    return np.minimum(r, b) - g - 0.5 * np.abs(r - b)


def key(img):
    """Retorna RGBA float com o fundo removido (unmix nas bordas)."""
    a = np.asarray(img.convert("RGB")).astype(np.float32)
    s = magentaness(a)
    bgcore = s > 120
    # fundo estimado localmente (o magenta tem gradientes)
    w = ndi.gaussian_filter(bgcore.astype(np.float32), 25) + 1e-4
    bg = np.stack([ndi.gaussian_filter(a[..., c] * bgcore, 25) / w for c in range(3)], -1)
    sbg = np.maximum(magentaness(bg), 60)
    ratio = s / sbg
    alpha = np.ones(s.shape, np.float32)
    alpha[ratio > 0.8] = 0.0
    # faixa de borda: perto do fundo, alpha linear pela "magentice" relativa
    near = ndi.binary_dilation(ratio > 0.8, iterations=2) & (ratio <= 0.8)
    edge_a = np.clip((0.8 - ratio) / 0.8, 0, 1)
    alpha[near] = np.minimum(1.0, edge_a[near] * 1.25)
    # pixels internos muito magentas e isolados do fundo ficam (corações rosa etc.)
    rgb = a.copy()
    m = (alpha > 0) & (alpha < 1)
    al = alpha[m][:, None]
    rgb[m] = np.clip((a[m] - (1 - al) * bg[m]) / np.maximum(al, 0.05), 0, 255)
    # sombras/fantasmas desenhados como magenta mais escuro (sombra do pulo, porta sumindo):
    # viram preto semitransparente em vez de uma mancha rosa
    mn, mnb = np.minimum(a[..., 0], a[..., 2]), np.minimum(bg[..., 0], bg[..., 2])
    shade = (alpha > 0) & (a[..., 1] < 0.35 * mn) & (np.abs(a[..., 0] - a[..., 2]) < 45) & (ratio > 0.15)
    rgb[shade] = 0
    alpha[shade] = np.clip(1 - mn[shade] / np.maximum(mnb[shade], 1), 0, 1) * 0.9
    # despill: perto do fundo, o azul acima do verde é contaminação magenta (cabelo vermelho fica vermelho)
    band = ndi.binary_dilation(ratio > 0.8, iterations=4) & (alpha > 0)
    r_, g_, b_ = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    lim = np.maximum(g_, np.minimum(r_ * 0.45, g_ + 25))
    b_[band] = np.minimum(b_[band], lim[band])
    spill = band & (np.minimum(a[..., 0], a[..., 2]) - a[..., 1] > 40)
    alpha[spill] *= 0.85
    # remove ruído pequeno
    lab, nl = ndi.label(alpha > 0.5)
    if nl:
        sizes = ndi.sum(np.ones_like(lab), lab, range(1, nl + 1))
        small = np.isin(lab, np.where(sizes < 40)[0] + 1)
        alpha[small] = 0
        alpha[ndi.binary_dilation(small, iterations=1) & (alpha < 0.5)] = 0
    return np.dstack([rgb, alpha * 255])


def segment(alpha, n, cuts=None):
    W = alpha.shape[1]
    prof = (alpha > 128).sum(0).astype(float)
    if cuts:
        xs = [0] + list(cuts) + [W]
        return [[xs[i], xs[i + 1]] for i in range(len(xs) - 1)]
    on = prof > 2
    segs, s = [], None
    for x, v in enumerate(on):
        if v and s is None:
            s = x
        if not v and s is not None:
            segs.append([s, x]); s = None
    if s is not None:
        segs.append([s, W])
    segs = [g for g in segs if g[1] - g[0] > 3]
    mass = [(alpha[:, a:b] > 128).sum() for a, b in segs]
    segs = [g for g, m in zip(segs, mass) if m > 0.01 * np.median(mass)]
    while len(segs) > n:  # junta pedaços pequenos (brilhos, sobras) ao vizinho mais próximo
        widths = [g[1] - g[0] for g in segs]
        i = int(np.argmin(widths))
        gl = segs[i][0] - segs[i - 1][1] if i > 0 else 1e9
        gr = segs[i + 1][0] - segs[i][1] if i < len(segs) - 1 else 1e9
        j = i - 1 if gl <= gr else i + 1
        a, b = sorted([i, j])
        segs[a] = [segs[a][0], segs[b][1]]
        del segs[b]
    if len(segs) < n:  # quadros grudados: acha os n corpos pelas pernas/tronco (separam melhor que o cabelo)
        rows = np.where((alpha > 128).sum(1) > 2)[0]
        top, bot = rows.min(), rows.max()
        legs = (alpha[int(top + 0.6 * (bot - top)):bot] > 128).sum(0).astype(float)
        unit = (segs[-1][1] - segs[0][0]) / n
        sm = ndi.gaussian_filter1d(legs, unit / 6)
        pk, sm2 = [], sm.copy()
        for _ in range(n):  # n picos com supressão de vizinhança
            p_ = int(np.argmax(sm2))
            pk.append(p_)
            sm2[max(0, p_ - int(unit * 0.4)):p_ + int(unit * 0.4)] = -1
        pk = sorted(pk)
        cuts = []
        for a_, b_ in zip(pk[:-1], pk[1:]):
            c = np.arange(a_, b_)
            mid = (a_ + b_) / 2
            cuts.append(int(c[np.argmin(prof[a_:b_] + 0.02 * np.abs(c - mid))]))
        xs = [segs[0][0]] + cuts + [segs[-1][1]]
        segs = [[xs[i], xs[i + 1]] for i in range(len(xs) - 1)]
    return segs


def main(ids):
    os.makedirs(OUT, exist_ok=True)
    os.makedirs(os.path.join(ROOT, "_preview"), exist_ok=True)
    fpath = os.path.join(ROOT, "assets", "frames.json")
    meta = json.load(open(fpath)) if os.path.exists(fpath) else {}
    tpath = os.path.join(ROOT, "assets", "consistency_targets.json")
    targets = json.load(open(tpath)) if os.path.exists(tpath) else {}
    for sid in ids:
        cfg = SHEETS[sid]
        tg = targets.get(str(sid), {})
        rgba = key(Image.open(os.path.join(SRC, FILES.get(sid, f"{sid}.png"))))
        rgba[..., :3] = correct_colors(rgba[..., :3], rgba[..., 3], tg)  # padroniza pele/mechas
        al = rgba[..., 3]
        segs = segment(al, cfg["n"], cfg.get("cuts"))
        info = []
        for x0, x1 in segs:
            sub = al[:, x0:x1] > 128
            lab, nl = ndi.label(sub)
            if not nl:
                info.append(None); continue
            sizes = ndi.sum(sub, lab, range(1, nl + 1))
            big = lab == (int(np.argmax(sizes)) + 1)
            ys, xs = np.where(big)
            bot, top = ys.max(), ys.min()
            band = xs[ys >= bot - (bot - top) * 0.06]
            if cfg.get("align") == "torso":
                tb = xs[(ys > top + (bot - top) * 0.35) & (ys < top + (bot - top) * 0.6)]
                band = np.array([tb.mean(), tb.mean()])
            yy, xx = np.where(al[:, x0:x1] > 8)
            info.append(dict(x0=x0, x1=x1, bh=bot - top, bot=bot,
                             fx=x0 + (band.min() + band.max()) / 2,
                             bb=(x0 + xx.min(), yy.min(), x0 + xx.max() + 1, yy.max() + 1)))
        ref = info[cfg.get("ref", 0)]
        scale = STAND_H / ref["bh"] * tg.get("mult", 1.0)  # padroniza tamanho da cabeça
        ground = float(np.median([f["bot"] for f in info if f]))
        d = os.path.join(OUT, f"s{sid:02d}")
        os.makedirs(d, exist_ok=True)
        for f in os.listdir(d):
            os.remove(os.path.join(d, f))
        img = Image.fromarray(rgba.astype(np.uint8), "RGBA")
        frames = []
        for k, f in enumerate(info):
            if f is None:
                frames.append(None); continue
            x0, y0, x1, y1 = f["bb"]
            crop = img.crop((x0, y0, x1, y1))
            w, h = max(1, round((x1 - x0) * scale)), max(1, round((y1 - y0) * scale))
            crop.resize((w, h), Image.LANCZOS).save(os.path.join(d, f"{k:02d}.png"), optimize=True)
            dx, dy = cfg.get("anchor", {}).get(k, [0, 0])
            frames.append(dict(file=f"s{sid:02d}/{k:02d}.png", w=w, h=h,
                               ox=round((x0 - f["fx"]) * scale) + dx + round(tg.get("dx", 0))
                               + round(tg.get("fdx", {}).get(str(k), 0)),  # cabeça estável (stabilize.py)
                               oy=round((y0 - ground) * scale) + dy + round(tg.get("dy", 0))))
        meta[str(sid)] = dict(scale=round(scale, 4), segs=segs, frames=frames, applied=tg)
        preview(sid, frames)
        print(sid, len(frames), "scale", round(scale, 3))
    json.dump(meta, open(fpath, "w"), indent=1)


def preview(sid, frames):
    """Quadros alinhados lado a lado + sobreposição (para checar tremor)."""
    cw, ch = 260, 420
    gx, gy = cw // 2, ch - 30
    n = len(frames)
    sheet = Image.new("RGBA", (cw * (n + 1), ch), (60, 60, 70, 255))
    dr = ImageDraw.Draw(sheet)
    onion = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    for k, f in enumerate(frames):
        if not f:
            continue
        im = Image.open(os.path.join(OUT, f["file"]))
        im = im.resize((f["w"] // 2 * 1 or 1, f["h"] // 2 or 1))
        pos = (k * cw + gx + f["ox"] // 2, gy + f["oy"] // 2)
        sheet.alpha_composite(im, pos)
        o = im.copy(); o.putalpha(o.getchannel("A").point(lambda v: v // 3))
        onion.alpha_composite(o, (gx + f["ox"] // 2, gy + f["oy"] // 2))
        dr.text((k * cw + 4, 4), str(k), fill=(255, 255, 0))
    sheet.alpha_composite(onion, (n * cw, 0))
    dr.line([(0, gy), (sheet.width, gy)], fill=(0, 255, 0))
    for k in range(n + 1):
        dr.line([(k * cw + gx, 0), (k * cw + gx, ch)], fill=(0, 120, 255))
    sheet.convert("RGB").save(os.path.join(ROOT, "_preview", f"aligned_{sid:02d}.png"))


if __name__ == "__main__":
    main([int(a) for a in sys.argv[1:]] or sorted(SHEETS))
