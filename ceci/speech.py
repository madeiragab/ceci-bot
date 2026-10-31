"""Falas da Ceci num balão que escreve letra a letra, como nos RPGs antigos.

Sem IA: frases fixas de assets/falas.json, sorteadas sem repetir até esgotar a categoria. Cada animação
tem a sua categoria (REACT) e fala no começo do miolo (ex.: já com o livro aberto). As interações do
mouse (clique, carinho, arraste, girada no ar, pouso, acordar) chegam pelo sinal `interaction` da janela e sempre
falam; as falas automáticas dependem de uma chance e de um intervalo mínimo entre elas.

Uma fala nunca corta a outra: o que chega com o balão ocupado entra na fila e é dito em sequência
(com uma pausa de leitura mais curta quando tem fala esperando). Fala automática com o balão ocupado
é só descartada. O balão é uma janela própria, transparente aos cliques, e só tem timer enquanto
escreve ou está na tela.
"""
import json
import os
import random
import time

from PySide6.QtCore import QObject, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPainterPath, QPen, QPolygonF
from PySide6.QtWidgets import QWidget

from .settings import ROOT

PATH = os.path.join(ROOT, "assets", "falas.json")

# animação -> (categoria, chance base, quando falar: índice do passo ou "core" = começo do miolo)
REACT = {
    "entrada": ("inicio", 1.0, 2),
    "curiosa": ("curiosa", 0.5, 0), "observando": ("curiosa", 0.5, 0),
    "idle_fofo": ("idle", 0.3, 0), "borda": ("idle", 0.5, "core"),
    "ajeitando": ("esperando", 0.4, 0),
    "fofa": ("apaixonada", 0.5, 0), "apaixonada": ("apaixonada", 0.7, 0),
    "beijinho": ("apaixonada", 0.7, 0), "coracao": ("apaixonada", 0.7, 0),
    "lendo": ("lendo", 0.7, "core"), "lendo_chao": ("lendo", 0.7, "core"),
    "cafe": ("cafe", 0.7, "core"), "caneca": ("cafe", 0.7, "core"),
    "sonolenta": ("sonolenta", 0.8, "core"),
    "cochilo": ("dormindo", 0.8, "core"), "dormindo": ("dormindo", 0.8, "core"),
    "acordando": ("acordando", 0.9, 2),
    "espreguicando": ("espreguicando", 0.8, 2),
    "feliz": ("feliz", 0.8, 0), "confusa": ("confusa", 0.8, 0), "assustada": ("assustada", 1.0, 0),
    "brava": ("brava", 0.8, 0), "negando": ("brava", 0.6, 0), "triste": ("triste", 0.8, "core"),
    "gato": ("gato", 0.8, 2),
    "pensando": ("interessante", 0.5, "core"), "processando": ("interessante", 0.5, "core"),
    "trabalhando": ("interessante", 0.4, "core"), "atualizando": ("interessante", 0.4, 0),
    "encontrando_bug": ("interessante", 0.5, 0), "apontando": ("interessante", 0.5, 0),
    "programando": ("interessante", 0.4, "core"), "programando_mesa": ("interessante", 0.4, "core"),
    "sucesso": ("comemorando", 0.7, 2), "aprovado": ("comemorando", 0.7, 4),
    "erro": ("deu_errado", 0.7, 2), "quebrou": ("deu_errado", 0.7, 3),
    "conversando": ("conversando", 0.8, 0), "explicando": ("conversando", 0.8, 0),
    "resumo": ("conversando", 0.5, "core"),
    "chamando": ("chamando", 0.8, 0), "lembrete": ("chamando", 0.7, 2), "prazo": ("chamando", 0.7, "core"),
    "escondendo": ("escondendo", 0.8, 4),
    "acenando": ("chamando", 0.0, 2),  # chance 0: só quando pedida (menu Interagir, painel)
    "carinho": ("carinho", 1.0, 0), "arrastada": ("arrastada", 1.0, 0),
}
PRIO = {"arrastada": 4, "girando": 4, "solta": 4, "tonta": 4, "saida": 5}  # interações valem 3; automáticas, 1; tchau fura a fila
QUEUE_MAX = 3
AUTO_GAP = 18.0  # s mínimos entre falas automáticas
CHAT = (45, 110)  # s entre comentários soltos quando está parada

FILL, BORDER, LINE, INK = QColor(255, 250, 244), QColor(58, 36, 52), QColor(236, 160, 178), QColor(43, 30, 40)
READ_MS = 900  # tempo para ler o fim da frase antes de ela sair correndo


def load_bank(path=PATH):
    with open(path, encoding="utf8") as f:
        return {k: v for k, v in json.load(f).items() if not k.startswith("_")}


class Bubble(QWidget):
    """Balão com rabicho apontando para a cabeça; escreve letra a letra, pisca ▼ e some."""
    ended = Signal()  # acabou o tempo de leitura: a próxima frase da fila entra no mesmo balão

    def __init__(self, settings):
        super().__init__(None)
        self.settings = settings
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.apply_flags()
        self.timer = QTimer(self, singleShot=True, timeout=self._tick)
        self.state, self.text, self.n, self.cat, self.prio = "off", "", 0, None, 0
        self.lines, self.blink, self.fade = [], False, 1.0
        self.tail, self.tail_at = "down", 0.0
        self.queued = False  # tem frase esperando: pausa de leitura curta
        self.set_scale(0.55)

    def apply_flags(self):
        f = Qt.FramelessWindowHint | Qt.Tool | Qt.NoDropShadowWindowHint | Qt.WindowTransparentForInput
        if self.settings["always_on_top"]:
            f |= Qt.WindowStaysOnTopHint
        vis = self.isVisible()
        self.setWindowFlags(f)
        if vis:
            self.show()

    def set_scale(self, scale):
        self.k = min(1.4, max(0.8, (scale / 0.55) ** 0.5))
        self.font_ = QFont("Segoe UI")
        self.font_.setPointSizeF(10.5 * self.k)
        self.font_.setWeight(QFont.DemiBold)
        self.fm = QFontMetricsF(self.font_)

    # --- estado ---
    def active(self):
        return self.state in ("typing", "hold")

    def typing(self):
        return self.state == "typing"

    def start(self, text, cat, prio):
        self.text, self.cat, self.prio, self.n = text, cat, prio, 0
        self._layout()
        self.blink, self.fade = False, 1.0
        self.setWindowOpacity(1.0)
        self.state = "typing"
        self.timer.start(70)

    def stop(self):
        self.timer.stop()
        self.state = "off"
        self.hide()

    def hurry(self):
        """Chegou frase na fila: termina de escrever esta e lê por menos tempo."""
        self.queued = True
        if self.state == "hold":
            self.hold_end = min(self.hold_end, time.monotonic() + self.short_hold(self.text) / 1000)

    def remaining_ms(self):
        """Até liberar o balão: o resto da escrita e a leitura (READ_MS no fim, curta com fila)."""
        if self.state == "typing":
            return self.type_ms(self.text[self.n:]) + (self.short_hold(self.text) if self.queued else READ_MS)
        if self.state == "hold":
            left = max(0, int((self.hold_end - time.monotonic()) * 1000))
            return left if self.queued else min(READ_MS, left)
        return 0

    @classmethod
    def type_ms(cls, text):
        return sum(cls._delay(c) for c in text)

    @staticmethod
    def short_hold(text):
        return int(min(2500, 900 + 25 * len(text)))

    @staticmethod
    def _delay(ch):
        if ch in ".!?…":
            return 220
        if ch in ",;:":
            return 120
        return 22 if ch == " " else 38

    def _tick(self):
        if self.state == "typing":
            self.n += 1
            self.update()
            if self.n < len(self.text):
                self.timer.start(self._delay(self.text[self.n - 1]))
                return
            self.state = "hold"
            hold = self.short_hold(self.text) / 1000 if self.queued else min(6.5, 1.5 + 0.055 * len(self.text))
            self.hold_end = time.monotonic() + hold
            self.timer.start(420)
        elif self.state == "hold":
            if time.monotonic() >= self.hold_end:
                self.ended.emit()
                if self.state == "hold":  # nada na fila: some devagar
                    self.state = "fade"
                    self.timer.start(30)
            else:
                self.blink = not self.blink
                self.update()
                self.timer.start(420)
        elif self.state == "fade":
            self.fade -= 0.15
            if self.fade <= 0:
                self.stop()
                return
            self.setWindowOpacity(self.fade)
            self.timer.start(30)

    # --- geometria ---
    def _layout(self):
        """Quebra as linhas pela frase inteira já no começo: as palavras não pulam de linha enquanto escreve."""
        maxw = 230 * self.k
        lines, cur = [], ""
        for word in self.text.split(" "):
            t = f"{cur} {word}" if cur else word
            if cur and self.fm.horizontalAdvance(t) > maxw:
                lines.append(cur)
                t = word
            cur = t
        self.lines = lines + [cur]
        k = self.k
        self.pad = (12 * k, 8 * k)
        tw = max(self.fm.horizontalAdvance(ln) for ln in self.lines)
        self.bw = max(48 * k, tw + 2 * self.pad[0] + 8 * k)  # + espaço do ▼
        self.bh = len(self.lines) * self.fm.lineSpacing() + 2 * self.pad[1]
        self.tl = 11 * k  # tamanho do rabicho

    def place(self, fx, top, head_y, area, s):
        """Em cima da cabeça; sem espaço em cima (arrastada lá no alto), ao lado da cabeça."""
        bw, bh, tl, r = self.bw, self.bh, self.tl, 10 * self.k
        if top - 3 * s - tl - bh >= area.top():
            self.tail, w, h = "down", bw, bh + tl
            x = min(max(fx - w / 2, area.left() + 4), area.right() - 4 - w)
            y = top - 3 * s - h
            self.tail_at = min(max(fx - x, r + 8), w - r - 8)
        else:
            right = fx + 55 * s + bw + tl <= area.right()
            self.tail, w, h = ("left" if right else "right"), bw + tl, bh
            x = fx + 55 * s if right else fx - 55 * s - w
            y = min(max(head_y - h / 2, area.top() + 4), area.bottom() - 4 - h)
            self.tail_at = min(max(head_y - y, r + 8), h - r - 8)
        if self.size().toTuple() != (int(w), int(h)):
            self.setFixedSize(int(w), int(h))
        self.move(int(round(x)), int(round(y)))
        self.update()

    def paintEvent(self, _):
        if self.state == "off":
            return
        k, tl = self.k, self.tl
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)
        w, h = self.width(), self.height()
        body = QRectF(1.5, 1.5, w - 3, h - 3)
        t, a = self.tail_at, 7 * k
        if self.tail == "down":
            body.setBottom(h - tl)
            tri = [QPointF(t - a, body.bottom() - 1), QPointF(t + a * 0.2, h - 1.5), QPointF(t + a, body.bottom() - 1)]
        elif self.tail == "left":
            body.setLeft(tl)
            tri = [QPointF(body.left() + 1, t - a), QPointF(1.5, t), QPointF(body.left() + 1, t + a)]
        else:
            body.setRight(w - tl)
            tri = [QPointF(body.right() - 1, t - a), QPointF(w - 1.5, t), QPointF(body.right() - 1, t + a)]
        r = 10 * k
        path = QPainterPath()
        path.addRoundedRect(body, r, r)
        tail = QPainterPath()
        tail.addPolygon(QPolygonF(tri))
        tail.closeSubpath()
        path = path.united(tail)
        p.setPen(QPen(BORDER, max(1.5, 2 * k)))
        p.setBrush(FILL)
        p.drawPath(path)
        p.setPen(QPen(LINE, 1))  # filete rosa por dentro, das mechas dela
        p.setBrush(Qt.NoBrush)
        inner = body.adjusted(3.5 * k, 3.5 * k, -3.5 * k, -3.5 * k)
        p.drawRoundedRect(inner, r - 3 * k, r - 3 * k)
        p.setFont(self.font_)
        p.setPen(INK)
        x0, y = body.left() + self.pad[0], body.top() + self.pad[1] + self.fm.ascent()
        start = 0
        for ln in self.lines:
            vis = ln[:max(0, self.n - start)]
            if vis:
                p.drawText(QPointF(x0, y), vis)
            start += len(ln) + 1
            y += self.fm.lineSpacing()
        if self.state == "hold" and not self.blink:  # ▼ de "continua", como nas caixas de diálogo
            cx, cy, d = body.right() - 10 * k, body.bottom() - 7 * k, 3.2 * k
            p.setPen(Qt.NoPen)
            p.setBrush(BORDER)
            p.drawPolygon(QPolygonF([QPointF(cx - d, cy - d), QPointF(cx + d, cy - d), QPointF(cx, cy + d * 0.6)]))
        p.end()


class Speech(QObject):
    def __init__(self, win, settings):
        super().__init__()
        self.win, self.s = win, settings
        self.bank = load_bank()
        self.bags, self.last_text = {}, {}
        self.bubble = Bubble(settings)
        self.pending = None
        self.muted = None  # animação que não deve puxar a fala automática dela (ex.: avisos da Sala Virtual)
        self.queue = []  # (categoria, prioridade, frase) esperando o balão liberar
        self.rel = None  # topo da cabeça em relação aos pés (com folga p/ não pular a cada quadro)
        self.last_auto = -1e9
        self.last_user = time.monotonic()
        self._idle_top = None
        self.chat = QTimer(self, singleShot=True, timeout=self._chat)
        win.player.frame.connect(self._on_frame)
        win.moved.connect(self.follow)
        win.interaction.connect(self._on_interaction)
        self.bubble.ended.connect(self._next)

    # --- frases ---
    def pick(self, cat):
        bag = self.bags.get(cat)
        if not bag:
            bag = list(self.bank.get(cat, []))
            random.shuffle(bag)
            if len(bag) > 1 and bag[-1] == self.last_text.get(cat):
                bag[0], bag[-1] = bag[-1], bag[0]  # não repete a última logo depois de reembaralhar
            self.bags[cat] = bag
        if not bag:
            return None
        self.last_text[cat] = bag.pop()
        return self.last_text[cat]

    def say(self, cat, prio=1, force=False, text=None):
        """Fala agora ou, com o balão ocupado, entra na fila (só interações; automática é descartada).

        `text` = frase pronta (ex.: nome e prazo de uma atividade) em vez de sortear da categoria."""
        w, b = self.win, self.bubble
        if not self.s["speech"] or not w.isVisible() or w.player.paused:
            return False
        if b.active():
            dup = (text in [q[2] for q in self.queue] if text
                   else cat in [q[0] for q in self.queue] or (cat == b.cat and b.typing()))
            if not force or dup:
                return False
            if prio >= 5:  # tchau: passa na frente do que estava esperando (sem cortar a frase atual)
                self.queue = []
            elif len(self.queue) >= QUEUE_MAX:
                return False
            text = text or self.pick(cat)
            if not text:
                return False
            self.queue.append((cat, prio, text))
            b.hurry()
            return True
        text = text or self.pick(cat)
        if not text:
            return False
        if not force:
            self.last_auto = time.monotonic()
        self._show(cat, prio, text)
        return True

    def _show(self, cat, prio, text):
        b = self.bubble
        b.set_scale(self.win.sprites.scale)
        b.queued = bool(self.queue)
        b.start(text, cat, prio)
        self.rel = None
        self.follow()
        b.show()
        self.restart_chat()

    def _next(self):
        w = self.win
        if self.queue and self.s["speech"] and w.isVisible() and not w.player.paused:
            self._show(*self.queue.pop(0))

    def _auto_ok(self, chance):
        f = self.s["speech_freq"]
        return (self.s["speech"] and time.monotonic() - self.last_auto > AUTO_GAP / max(0.2, f)
                and random.random() < min(1.0, chance * f))

    # --- ganchos ---
    def _on_frame(self, st, new):
        p = self.win.player
        if new:
            forced = self.win.talk_aid == p.aid
            self.win.talk_aid = None
            self.pending = None
            r = REACT.get(p.aid) if self.muted != p.aid else None  # quem pediu a animação já fala por ela
            self.muted = None
            if r and (forced or self._auto_ok(r[1])):
                a = p.current
                at = (a["loop"][0] if a.get("loop") else 0) if r[2] == "core" else r[2]
                self.pending = (p.aid, at, r[0], forced)
        if self.pending and self.pending[0] == p.aid and p.i >= self.pending[1]:
            _, _, cat, forced = self.pending
            self.pending = None
            self.say(cat, 3 if forced else 1, force=forced)
        elif self.bubble.active():
            self.follow()

    def _on_interaction(self, kind):
        self.last_user = time.monotonic()
        if kind == "olhando":
            if self._auto_ok(0.35):
                self.say("curiosa")
            return
        self.say(kind, PRIO.get(kind, 3), force=True)

    def follow(self):
        b, w = self.bubble, self.win
        if not b.active() and b.state != "fade":
            return
        s = w.sprites.scale
        if self._idle_top is None or self._idle_top[0] != s:
            m = w.sprites.info(57, 0)
            self._idle_top = (s, m["oy"] * s if m else -330 * s)
        top = self._idle_top[1]
        rel = max(top, w.cur.oy) if w.cur else top  # sentada/agachada: desce junto; pulo/ícones: não sobe
        if self.rel is None or abs(rel - self.rel) > 30 * s:
            self.rel = rel
        b.place(w.foot.x(), w.foot.y() + self.rel, w.foot.y() - 285 * s, w.area(), s)

    def _chat(self):
        w = self.win
        if not w.exiting and not w.dragging and not self.bubble.active():
            if w.player.aid in ("cochilo", "dormindo") and w.player.in_core():
                self.say("dormindo")
            elif w.is_idle():
                r = random.random()
                idle_for = time.monotonic() - self.last_user
                self.say("raras" if r < 0.08 else "esperando" if idle_for > 180 and r < 0.45 else "idle")
        self.restart_chat()

    def restart_chat(self):
        w = self.win
        if self.s["speech"] and w.isVisible() and not w.player.paused and not w.exiting:
            self.chat.start(int(random.uniform(*CHAT) / max(0.2, self.s["speech_freq"]) * 1000))
        else:
            self.chat.stop()

    # --- controle ---
    def remaining_ms(self):
        """Até terminar de dizer tudo o que está na fila (e dar tempo de ler a última frase)."""
        ms = self.bubble.remaining_ms() if self.bubble.active() else 0
        for i, (_, _, text) in enumerate(self.queue):
            last = i == len(self.queue) - 1
            ms += 70 + Bubble.type_ms(text) + (READ_MS if last else Bubble.short_hold(text))
        return ms

    def hide(self):
        self.pending = None
        self.queue = []
        self.bubble.stop()
        self.chat.stop()

    def apply_settings(self):
        self.bubble.apply_flags()
        if not self.s["speech"]:
            self.hide()
        else:
            self.restart_chat()
