"""Carrega quadros sob demanda, já escalados p/ o tamanho atual, com cache LRU pequeno."""
import json
import os
from collections import OrderedDict

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap, QTransform

from .settings import ROOT

ASSETS = os.path.join(ROOT, "assets")


class Frame:
    __slots__ = ("pix", "ox", "oy", "w", "h")

    def __init__(self, pix, ox, oy, w, h):
        self.pix, self.ox, self.oy, self.w, self.h = pix, ox, oy, w, h


class Sprites:
    def __init__(self, scale, dpr=1.0, cache_size=96):
        self.meta = json.load(open(os.path.join(ASSETS, "frames.json"), encoding="utf8"))
        self.anims = json.load(open(os.path.join(ASSETS, "animations.json"), encoding="utf8"))
        self.cache = OrderedDict()
        self.cache_size = cache_size
        self.set_scale(scale, dpr)

    def set_scale(self, scale, dpr=None):
        self.scale = scale
        if dpr:
            self.dpr = dpr
        self.cache.clear()

    def info(self, sheet, idx):
        fr = self.meta.get(str(sheet), {}).get("frames", [])
        return fr[idx] if 0 <= idx < len(fr) else None

    def get(self, sheet, idx, mirror=False):
        """Frame com pixmap escalado; ox/oy/w/h em px lógicos relativos ao ponto dos pés."""
        key = (sheet, idx, mirror)
        f = self.cache.get(key)
        if f is not None:
            self.cache.move_to_end(key)
            return f
        m = self.info(sheet, idx)
        if m is None:
            return None
        s = self.scale
        w, h = max(1, round(m["w"] * s)), max(1, round(m["h"] * s))
        img = QImage(os.path.join(ASSETS, "sprites", m["file"]))
        if img.isNull():
            return None
        img = img.scaled(round(w * self.dpr), round(h * self.dpr), Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
        if mirror:
            img = img.transformed(QTransform().scale(-1, 1))
        pix = QPixmap.fromImage(img)
        pix.setDevicePixelRatio(self.dpr)
        ox = m["ox"] * s
        if mirror:
            ox = -(ox + w)
        f = Frame(pix, ox, m["oy"] * s, w, h)
        self.cache[key] = f
        if len(self.cache) > self.cache_size:
            self.cache.popitem(last=False)
        return f
