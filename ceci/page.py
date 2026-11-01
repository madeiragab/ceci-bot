"""O que tem dentro da janela do navegador (botões, imagens, campos, cartões), só lendo: a Ceci sobe e senta neles
como senta nas janelas.

Usa o UI Automation do Windows (a mesma interface dos leitores de tela): pega só o tipo, o nome e o retângulo de
cada coisa visível da página. Nunca clica, digita, foca nem lê o texto digitado; não lê a página em si (nada vai
pra IA nem pro disco). Roda numa thread própria (o COM do UIA não pode travar a tela), só com o navegador na frente
ou quando ela está sentada num item, e para quando "Sentar nas janelas" está desligado.
"""
import re
import threading
import time
from dataclasses import dataclass

from . import desktop

REFRESH = 0.8        # s entre leituras da página (navegador na frente)
MIN_W, MIN_H = 70, 18  # px nativos: menores que isso não dá pra sentar
MAX_ITEMS = 300
COUNT = re.compile(r"^\(\d+\+?\)\s*")  # "(3) YouTube": contador de notificação não é página nova
KINDS = {}           # id do tipo de controle do UIA -> nome curto (preenchido quando o UIA carrega)


@dataclass(frozen=True)
class Item:
    """Coisa da página com retângulo nativo (Win32)."""
    hwnd: int
    kind: str
    name: str
    left: int
    top: int
    right: int
    bottom: int

    @property
    def key(self):
        return f"{self.kind}:{self.name[:60]}:{(self.right - self.left) // 8}"


def pick(raw, doc, min_w=MIN_W, min_h=MIN_H, limit=MAX_ITEMS):
    """Filtra o que dá para sentar: dentro da página visível, largo o bastante e sem repetir a mesma borda."""
    dl, dt, dr, db = doc
    out, seen = [], set()
    for it in sorted(raw, key=lambda i: (i.top, i.left)):
        w, h = it.right - it.left, it.bottom - it.top
        if w < min_w or h < min_h or it.top <= dt or it.top >= db - 8 or it.right <= dl or it.left >= dr:
            continue
        if w > (dr - dl) * 0.97:  # faixa da página inteira (corpo, cabeçalho): não é "um botão"
            continue
        sig = (it.top // 4, it.left // 12, it.right // 12)
        if sig in seen:
            continue
        seen.add(sig)
        out.append(it)
        if len(out) >= limit:
            break
    return out


class Page:
    """Lê os itens da janela do navegador da frente (ou da janela onde ela está sentada) numa thread."""

    def __init__(self):
        self.items, self.hwnd, self.at = [], None, 0.0
        self.on = False
        self.track = None  # hwnd onde ela está sentada (segue lendo mesmo sem estar na frente)
        self.fg = None     # navegador da frente (a thread da tela atualiza; desktop.foreground usa o Qt)
        self.error = None
        self.gen = 0       # muda quando a página da janela muda (outra aba, outro site): itens antigos não valem
        self._wake = threading.Event()
        self._stop = False
        self._thread = None

    # --- chamado da thread da tela ---
    def set_on(self, on):
        self.on = bool(on)
        if self.on and desktop.ON and self._thread is None:
            self._thread = threading.Thread(target=self._run, name="ceci-page", daemon=True)
            self._thread.start()
        if not self.on:
            self.items, self.hwnd = [], None
        self._wake.set()

    def close(self):
        self._stop = True
        self._wake.set()

    def poke(self):
        """Lê agora (ex.: ela vai escolher onde subir)."""
        self._wake.set()

    def fresh(self, hwnd, age=2.5):
        return self.hwnd == hwnd and time.monotonic() - self.at < age

    def surfaces(self, hwnd=None, min_width=60, top_margin=0):
        """Bordas de cima dos itens da janela (lógicas), no mesmo formato das janelas (desktop.Surface)."""
        if not self.on or not self.items or (hwnd is not None and self.hwnd != hwnd):
            return []
        out, scr = [], desktop._screens()
        for it in self.items:
            a, b = desktop.to_logical(it.left, it.top, scr), desktop.to_logical(it.right - 1, it.top, scr)
            if b.x() - a.x() < min_width or a.y() < top_margin:
                continue
            out.append(desktop.Surface(it.hwnd, a.y(), a.x(), b.x(), it.name or it.kind, el=it.key))
        return out

    def find(self, surf, x=None, max_dy=None):
        """O mesmo item de antes na leitura mais nova (rolou a página: mudou de lugar). None = sumiu, ou só tem
        um parecido longe demais (outro item igual na página: não teleporta pra ele)."""
        best = None
        for sf in self.surfaces(surf.hwnd):
            if sf.el == surf.el and (x is None or sf.x0 - 2 <= x <= sf.x1 + 2):
                if best is None or abs(sf.y - surf.y) < abs(best.y - surf.y):
                    best = sf
        if best is not None and max_dy is not None and abs(best.y - surf.y) > max_dy:
            return None
        return best

    # --- thread ---
    def _run(self):
        try:
            import comtypes
            import comtypes.client
            comtypes.CoInitialize()
            try:
                from comtypes.gen import UIAutomationClient as U
            except ImportError:
                comtypes.client.GetModule("UIAutomationCore.dll")
                from comtypes.gen import UIAutomationClient as U
            uia = comtypes.client.CreateObject(U.CUIAutomation, interface=U.IUIAutomation)
        except Exception as e:  # sem UIA: ela só senta nas janelas, como antes
            self.error = f"UIA indisponível: {e}"
            return
        KINDS.update({U.UIA_ButtonControlTypeId: "botão", U.UIA_ImageControlTypeId: "imagem",
                      U.UIA_EditControlTypeId: "campo", U.UIA_ComboBoxControlTypeId: "lista",
                      U.UIA_HyperlinkControlTypeId: "link", U.UIA_ListItemControlTypeId: "item",
                      U.UIA_TabItemControlTypeId: "aba"})
        cond = uia.CreateAndCondition(
            uia.CreateOrConditionFromArray([uia.CreatePropertyCondition(U.UIA_ControlTypePropertyId, k)
                                            for k in KINDS]),
            uia.CreatePropertyCondition(U.UIA_IsOffscreenPropertyId, False))
        is_doc = uia.CreatePropertyCondition(U.UIA_ControlTypePropertyId, U.UIA_DocumentControlTypeId)
        req = uia.CreateCacheRequest()
        for p in (U.UIA_BoundingRectanglePropertyId, U.UIA_ControlTypePropertyId, U.UIA_NamePropertyId):
            req.AddProperty(p)
        docs, titles = {}, {}
        while not self._stop:
            self._wake.wait(REFRESH)
            self._wake.clear()
            if self._stop:
                break
            if not self.on:
                continue
            try:
                hwnd = self.track or self.fg
                if not hwnd:
                    self.items, self.hwnd = [], None
                    continue
                title = COUNT.sub("", desktop._title(hwnd))
                if titles.get(hwnd, title) != title:  # trocou de aba/página: documento novo, itens novos
                    docs.pop(hwnd, None)
                    self.items, self.gen = [], self.gen + 1
                titles = {hwnd: title}
                doc = docs.get(hwnd)
                if doc is None:  # achar o documento também liga a árvore da página no Chromium
                    doc = uia.ElementFromHandle(hwnd).FindFirst(U.TreeScope_Descendants, is_doc)
                    if not doc:
                        continue
                    docs = {hwnd: doc}
                r = doc.CurrentBoundingRectangle
                box = (r.left, r.top, r.right, r.bottom)
                if box[2] - box[0] < MIN_W:
                    docs.pop(hwnd, None)
                    continue
                arr = doc.FindAllBuildCache(U.TreeScope_Descendants, cond, req)
                raw = []
                for i in range(min(arr.Length, 1500)):
                    e = arr.GetElement(i)
                    b = e.CachedBoundingRectangle
                    raw.append(Item(hwnd, KINDS.get(e.CachedControlType, "?"), (e.CachedName or "").strip(),
                                    b.left, b.top, b.right, b.bottom))
                self.items, self.hwnd, self.at = pick(raw, box), hwnd, time.monotonic()
                self.error = None
            except Exception as e:  # janela fechou, página trocando: tenta na próxima
                docs = {}
                self.error = str(e)[:200]
