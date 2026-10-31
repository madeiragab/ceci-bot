"""Folha de conferência: cada passagem ENTRE folhas (entrada/saída/emendas) desenhada como o
meio do dissolve (50% + 50%), no ponto dos pés. Fantasma duplo = salto visível.

Uso: python -I tools/overlay.py  → _preview/trans_1.png, trans_2.png ...
"""
import json
import os

from PIL import Image, ImageDraw

from transitions import pairs

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
A = os.path.join(ROOT, "assets")
CW, CH, GY, SC, COLS, PER = 150, 215, 200, 0.5, 10, 50


def main():
    anims = json.load(open(os.path.join(A, "animations.json"), encoding="utf8"))
    meta = json.load(open(os.path.join(A, "frames.json"), encoding="utf8"))

    def layer(sf):
        f = meta[str(sf[0])]["frames"][sf[1]]
        im = Image.open(os.path.join(A, "sprites", f["file"])).convert("RGBA")
        im = im.resize((max(1, int(im.width * SC)), max(1, int(im.height * SC))), Image.LANCZOS)
        c = Image.new("RGBA", (CW, CH), (0, 0, 0, 0))
        c.alpha_composite(im, (max(0, CW // 2 + int(f["ox"] * SC)), max(0, GY + int(f["oy"] * SC))))
        return c

    cells, seen = [], set()
    for aid, kind, x, y in pairs(anims):
        if x[0] == y[0] or (x, y) in seen:
            continue
        seen.add((x, y))
        a, b = layer(x), layer(y)
        mix = Image.blend(a, b, 0.5)
        cell = Image.new("RGBA", (CW, CH), (58, 60, 70, 255))
        cell.alpha_composite(mix)
        d = ImageDraw.Draw(cell)
        d.line([(0, GY), (CW, GY)], fill=(0, 170, 0))
        d.text((2, 2), "%s %s" % (aid[:12], kind[:3]), fill=(255, 255, 0))
        d.text((2, 13), "%d.%d>%d.%d" % (x + y), fill=(200, 200, 200))
        cells.append(cell)
    for n in range(0, len(cells), PER):
        part = cells[n:n + PER]
        rows = (len(part) + COLS - 1) // COLS
        out = Image.new("RGB", (CW * COLS, CH * rows), (30, 30, 30))
        for i, c in enumerate(part):
            out.paste(c, ((i % COLS) * CW, (i // COLS) * CH))
        out.save(os.path.join(ROOT, "_preview", "trans_%d.png" % (n // PER + 1)))
    print(len(cells), "passagens entre folhas")


if __name__ == "__main__":
    main()
