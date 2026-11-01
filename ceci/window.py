"""Janela transparente da Ceci: desenho, posição, movimento e interações com o mouse."""
import math
import random
import time
from dataclasses import replace

from PySide6.QtCore import QPoint, QPointF, QRect, Qt, QTimer, Signal
from PySide6.QtGui import QCursor, QGuiApplication, QPainter
from PySide6.QtWidgets import QWidget

from . import desktop, mood
from .engine import Player
from .sprites import Sprites

CANVAS_W, CANVAS_H, FOOT_MARGIN = 640, 590, 100  # em px de sprite (escala 1.0); margem: pernas na barra
DRAG_START, DRAG_QUICK, DRAG_HOLD = 6, 22, 0.25  # px parado/segurando; px num clique rápido; s até "segurar"
INTERACT = tuple(mood.HAPPY["clique"]) + ("brava",)  # reações a clique ou menu Interagir (ceci/mood.py)
PET = tuple(mood.HAPPY["carinho"]) + ("brava",)       # reações a carinho
PET_PASSES, PET_STROKE, PET_WINDOW = 5, 30, 3.0  # carinho: 5 idas e vindas (≥ 30 px) no MESMO eixo em 3 s
PET_CONFIRM = 450  # ms: clicou logo depois? era só a mira chegando nela — vale o clique, não o carinho
SPIN_WINDOW, SPIN_PATH, SPIN_TURN = 1.5, 500, 3 * math.pi  # girada/sacudida: 1,5 volta (ou 3 idas e vindas)
SPIN_AGAIN = 6.0  # s até poder reclamar de novo se continuar girando
EYE_HOLD = 1.5       # s mínimos olhando numa direção antes de trocar
EYE_COOLDOWN = 10.0  # s depois de parar de olhar o mouse até poder começar de novo
FADE_MS = 420  # troca de animação: desenhos diferentes precisam de um dissolve mais longo
FALL_G, JUMP_G = 2600, 1900  # px/s²: queda (soltou no ar, a janela sumiu) e pulo (mais leve, dá pra ver o arco)
MAX_JUMP = 2800   # px de sprite (escala 1.0): até onde ela pula sozinha para cima (dá a tela toda no tamanho mínimo)
HEADROOM = 345    # px de sprite acima dos pés: o espaço que ela ocupa em pé em cima de uma borda
SIT_ROOM = 215    # ... e sentada: borda colada no topo da tela (vídeo flutuante) só dá pra ficar sentada
PERCH_MS, PERCH_CHECK = 50, 0.6  # sentada numa janela: segue ela a cada 50 ms; confere se a borda está livre a cada 0,6 s


class CeciWindow(QWidget):
    context_menu = Signal(QPoint)
    became_idle = Signal()
    moved = Signal()
    interaction = Signal(str)  # clique, carinho, arrastada, girando, solta, tonta, acordando, olhando, caiu, janela
    double_clicked = Signal()  # clique duplo nela: caixinha para digitar
    files_dropped = Signal(list)  # arquivos soltos em cima dela (caminhos)

    def __init__(self, settings):
        super().__init__(None)
        self.settings = settings
        self._apply_flags()
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setMouseTracking(True)
        self.setAcceptDrops(True)
        self.setWindowTitle("Ceci")

        screen = QGuiApplication.primaryScreen()
        self.sprites = Sprites(settings["size"], screen.devicePixelRatio())
        self.player = Player(self.sprites.anims, settings)
        self.player.frame.connect(self._on_frame)
        self.player.finished.connect(self._on_finished)

        self.cur = None          # Frame atual
        self.step = None
        self.prev = None         # Frame anterior p/ transição suave
        self.prev_shift = QPointF()  # onde ele estava em relação aos pés atuais (pés presos à borda mudam)
        self.fade_t0 = 0.0
        self.fade_ms = FADE_MS
        self.fade_timer = QTimer(self, timeout=self._fade_tick)

        self.foot = QPointF(0, 0)   # ponto dos pés em coordenadas lógicas da tela
        self.vel = 0.0              # px/s horizontal (caminhada / passos com "mv")
        self.walk_target = None
        self.walk_speed = 0.0
        self.fall_v = None          # velocidade vertical no ar (queda após soltar o arraste, pulo, janela que sumiu)
        self.air_vx, self.air_g, self.flight = 0.0, FALL_G, None  # no ar: px/s de lado, gravidade, "pulo"/"queda"
        self.after_land = None      # o que fazer depois de pousar (ex.: descer da janela e ir para o canto)
        self.perch = None           # borda de cima da janela onde ela está (desktop.Surface); None = no chão
        self.perch_rect = None      # retângulo da janela na última conferida (para seguir quando você arrasta)
        self.perch_t = 0.0          # quando subiu (o comportamento decide descer depois de um tempo)
        self.perch_check = 0.0
        self.surfaces = []          # bordas onde dá para pousar nesta queda/pulo
        self.page = None            # itens da página do navegador (ceci/page.py); o App liga
        self.perch_timer = QTimer(self, timeout=self._perch_tick)
        self.last_move = time.monotonic()
        self.move_timer = QTimer(self, timeout=self._move_tick)

        self.press, self.press_t = None, 0.0
        self.dragging = False
        self.drag_off = QPointF()
        self._reset_rub()
        self.last_pet = 0.0
        self.pet_timer = QTimer(self, singleShot=True, timeout=self.pet)
        # clique simples espera o tempo do clique duplo do Windows: o duplo abre a caixinha sem fazer ela interagir
        self.click_timer = QTimer(self, singleShot=True, timeout=self._click,
                                  interval=QGuiApplication.styleHints().mouseDoubleClickInterval())
        self.eyes_on = False
        self.eyes_idx = None
        self.mood = mood.Mood()
        self.eyes_last_near = 0.0
        self.eye_timer = QTimer(self, timeout=self._eye_tick)
        self.exiting = False
        self.talk_aid = None        # animação pedida pelo usuário: a fala dela não depende de sorteio
        self.breath_timer = QTimer(self, timeout=self.update)  # respiração sutil (nunca fica "congelada")
        self._resize_canvas()

    # ---------- configuração ----------
    def _apply_flags(self):
        f = Qt.FramelessWindowHint | Qt.Tool | Qt.NoDropShadowWindowHint
        if self.settings["always_on_top"]:
            f |= Qt.WindowStaysOnTopHint
        vis = self.isVisible()
        self.setWindowFlags(f)
        if vis:
            self.show()

    def apply_settings(self):
        self._apply_flags()
        self.set_size(self.settings["size"])
        self.update_eye_timer()
        self.update_breath()

    def update_breath(self):
        on = self.settings.get("breathe", True) and not self.settings["eco"] and self.isVisible()             and not self.player.paused
        if on and not self.breath_timer.isActive():
            self.breath_timer.start(83)  # ~12 fps basta p/ um movimento de 3,4 s
        elif not on:
            self.breath_timer.stop()

    def set_size(self, s):
        self.settings["size"] = s
        self.sprites.set_scale(s, self.devicePixelRatioF() or None)
        self._resize_canvas()
        if self.step:
            self.cur = self._frame(self.step)
        self._place()

    def _resize_canvas(self):
        s = self.sprites.scale
        self.anchor = QPointF(CANVAS_W * s / 2, (CANVAS_H - FOOT_MARGIN) * s)
        self.setFixedSize(int(CANVAS_W * s), int(CANVAS_H * s))

    # ---------- geometria ----------
    def area(self, p=None):
        p = p or self.foot
        sc = QGuiApplication.screenAt(QPoint(int(p.x()), int(p.y()) - 5)) or self.screen() \
            or QGuiApplication.primaryScreen()
        return sc.availableGeometry()

    def ground(self):
        return self.perch.y if self.perch else self.area().bottom() + 1

    def span(self):
        """Onde ela pode andar: a borda da janela em que está, ou a largura da tela."""
        if self.perch:
            return self.perch.x0, self.perch.x1
        a = self.area()
        return a.left(), a.right()

    def headroom(self):
        return int(HEADROOM * self.sprites.scale)

    def sit_room(self):
        return int(SIT_ROOM * self.sprites.scale)

    def low(self):
        """Em cima de uma janela colada no topo da tela (ex.: vídeo flutuante): em pé a cabeça sairia da tela."""
        return bool(self.perch) and self.perch.y < self.area().top() + self.headroom()

    def sit_low(self):
        """Senta e fica sentada (sem voltar a ficar em pé a cada volta da animação, nem olhar o mouse em pé)."""
        if self.low() and not self.dragging and self.fall_v is None and not self.exiting:
            self.low_until = time.monotonic() + random.uniform(120, 300)
            self.play("borda", force=True, loops="inf")

    def clamp_x(self, x, margin=None):
        left, right = self.span()
        m = (40 if self.perch else 45) * self.sprites.scale if margin is None else margin
        m = min(m, (right - left) / 2)
        return min(max(x, left + m), right - m)

    def set_start_pos(self):
        s, a = self.settings, QGuiApplication.primaryScreen().availableGeometry()
        off = 120 * self.sprites.scale
        if s["start_pos"] == "saved" and s["pos"]:
            self.foot = QPointF(*s["pos"])
            if not QGuiApplication.screenAt(self.foot.toPoint() - QPoint(0, 5)):
                self.foot = QPointF(a.right() - off, a.bottom() + 1)
        elif s["start_pos"] == "bottom_left":
            self.foot = QPointF(a.left() + off, a.bottom() + 1)
        else:
            self.foot = QPointF(a.right() - off, a.bottom() + 1)
        self.foot.setY(self.ground())
        self._place()

    def move_to_corner(self, corner):
        a = self.area()
        off = 120 * self.sprites.scale
        x = a.left() + off if corner == "left" else a.right() - off
        if self.perch:  # em cima de uma janela: pula para o chão primeiro
            return self.jump_to(None, self.foot.x(), then=lambda: self.walk_to(x, fast=True))
        self.walk_to(x, fast=True)  # sempre andando (nada de teleporte), mesmo com a caminhada automática desligada

    def _jump(self, x):
        self.foot = QPointF(x, self.ground())
        self._place()
        self.save_pos()

    def save_pos(self):
        self.settings["pos"] = [round(self.foot.x()), round(self.foot.y())]
        self.settings.save()

    def _place(self):
        p = self.foot - self.anchor
        self.move(int(round(p.x())), int(round(p.y())))
        self.moved.emit()

    # ---------- desenho ----------
    def _frame(self, st):
        if st[0] == 0:
            return None
        return self.sprites.get(st[0], st[1], self.player.mirror)

    def _on_frame(self, st, new):
        old, old_st = self.cur, self.step
        self.step = st
        self.cur = self._frame(st)
        ex = st[3] if len(st) > 3 else {}
        old_foot = QPointF(self.foot)
        if "pin" in ex and self.cur:
            # encosta a borda do quadro na borda da tela (saída / esconder); espelhada = borda esquerda
            d = ex.get("dx", 0) * self.sprites.scale
            if self.player.mirror:
                self.foot.setX(self.area().left() - self.cur.ox - d)
            else:
                self.foot.setX(self.area().right() + 1 - (self.cur.ox + self.cur.w) + d)
            self._place()
        a = self.player.current
        if "mv" in ex:
            self.vel = ex["mv"] * self.sprites.scale * (-1 if self.player.mirror else 1)
        elif a and a.get("walk") and self.walk_target is not None and a["loop"][0] <= self.player.i <= a["loop"][1]:
            self.vel = self.walk_speed  # só desliza durante o ciclo de pernas (não no virar/parar)
        else:
            self.vel = 0.0
        if self.vel or self.fall_v is not None:
            self._start_move()
        self.prev = None
        if old is not None and old is not self.cur and not self.settings["eco"] and not self.dragging:
            # toda troca de pose dissolve suavemente (sem "slideshow"); troca de animação um pouco mais longa
            dur = st[2] / max(0.1, self.settings["speed"])
            ran = bool(old_st) and len(old_st) > 3 and "mv" in old_st[3]  # saindo da corrida: corte seco também
            walking = (self.player.current and self.player.current.get("walk")) or "mv" in ex or ran
            # quadros com deslocamento (andar/correr): sem dissolve, senão um "fantasma" arrasta atrás dela
            if new:
                self.fade_ms = 120 if "mv" in ex else FADE_MS
            else:
                self.fade_ms = 0 if walking else min(FADE_MS, max(60, dur * 0.5))
            self.prev = old if self.fade_ms else None
            self.prev_shift = old_foot - self.foot  # o quadro antigo some no lugar dele, sem pular
            self.fade_t0 = time.monotonic()
            self.fade_timer.start(max(16, 1000 // self.settings["fps"]))
        if ex.get("sit") and self.settings["always_on_top"]:
            self.raise_()  # pernas por cima da barra de tarefas: não deixa a barra cobrir
        if self.fall_v is not None and a and self.player.i == a.get("fall"):
            self.player.timer.stop()  # segura o quadro "caindo" até tocar o chão
        self.update()

    def _fade_tick(self):
        if time.monotonic() - self.fade_t0 >= self.fade_ms / 1000:
            self.prev = None
            self.fade_timer.stop()
        self.update()

    def paintEvent(self, _):
        if not self.cur and not self.prev:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        t = 1.0
        if self.prev:
            # dissolve sem "buraco" de transparência: pose antiga some por baixo, nova surge por cima
            t = min(1.0, (time.monotonic() - self.fade_t0) / (self.fade_ms / 1000))
            p.setOpacity(min(1.0, 2 - 2 * t))
            self._draw(p, self.prev, self.prev_shift)
        if self.cur:
            p.setOpacity(min(1.0, 2 * t))
            self._draw(p, self.cur)
        p.end()

    def _draw(self, p, f, shift=QPointF()):
        pos = QPointF(self.anchor.x() + f.ox, self.anchor.y() + f.oy) + shift
        k = self._breath()
        if k:  # peito sobe/desce ~1%, ancorado nos pés (o desenho não muda)
            p.save()
            p.translate(self.anchor)
            p.scale(1 - k * 0.3, 1 + k)
            p.translate(-self.anchor)
            p.drawPixmap(pos, f.pix)
            p.restore()
        else:
            p.drawPixmap(pos, f.pix)

    def _breath(self):
        if not self.breath_timer.isActive() or self.dragging or self.vel or self.fall_v is not None:
            return 0.0
        return 0.009 * (0.5 - 0.5 * math.cos(2 * math.pi * time.monotonic() / 3.4))

    # ---------- reprodução ----------
    def play(self, aid, **kw):
        if self.exiting and aid != "saida":
            return False
        here = kw.pop("here", False)
        if self.sprites.anims.get(aid, {}).get("edge") and not here:
            if self.perch:
                return False  # presa à parede da tela: em cima de uma janela não tem parede
            x = self.edge_start(aid)
            if abs(x - self.foot.x()) > 8:
                # depende da parede: anda até lá primeiro, e só então faz a animação (nada de teleporte)
                self.walk_to(x, on_done=lambda: self.play(aid, here=True, **{**kw, "force": True}), fast=True)
                return True
        self.eyes_off()
        if kw.pop("talk", False):
            self.talk_aid = aid
        return self.player.play(aid, mirror=kw.pop("mirror", False), **kw)

    def edge_start(self, aid):
        """Onde começar uma animação presa à parede: depois dos passos dela ("mv"), o último quadro solto
        encosta na borda da tela, e o primeiro quadro preso ("pin") continua dali sem pular."""
        a, s = self.sprites.anims[aid], self.sprites.scale
        seq = a["seq"]
        p = next(i for i, st in enumerate(seq) if len(st) > 3 and "pin" in st[3])
        f = self.sprites.get(seq[p - 1][0], seq[p - 1][1])
        dist = sum(st[3]["mv"] * s * st[2] / 1000 / max(0.1, self.settings["speed"])
                   for st in seq[:p] if len(st) > 3 and "mv" in st[3])
        return self.area().right() + 1 - (f.ox + f.w) - dist

    def is_idle(self):
        return self.player.aid == "idle" and not self.dragging and not self.eyes_on

    def _on_finished(self, aid):
        if aid == "caminhar":
            self.walk_target = None
            self.vel = 0
        QTimer.singleShot(0, self._check_idle)

    def _check_idle(self):
        if self.player.aid == "idle":
            self.became_idle.emit()

    # ---------- movimento ----------
    def walk_to(self, x, on_done=None, fast=False):
        x = self.clamp_x(x)
        if abs(x - self.foot.x()) < 8:
            if on_done:
                on_done()
            return
        left = x < self.foot.x()
        self.walk_target = x
        self._walk_done = on_done
        # velocidade casada com a passada real (px por ciclo de 2 passos), p/ os pés não patinarem
        a = self.sprites.anims["caminhar"]
        i0, i1 = a["loop"]
        cycle = sum(st[2] for st in a["seq"][i0:i1 + 1]) / 1000 / max(0.1, self.settings["speed"])
        speed = a["stride"] * self.sprites.scale / cycle * (1.3 if fast else 1.0)
        self.walk_speed = -speed if left else speed
        self.play("caminhar", mirror=left, force=True)

    def stop_walk(self):
        if self.walk_target is not None:
            self.walk_target = None
            self.vel = 0
            self.player.stop(graceful=True)

    def _start_move(self):
        if not self.move_timer.isActive():
            self.last_move = time.monotonic()
            self.move_timer.start(max(16, 1000 // self.settings["fps"]))

    def _move_tick(self):
        now = time.monotonic()
        dt, self.last_move = min(0.1, now - self.last_move), now
        if self.fall_v is not None:
            y0 = self.foot.y()
            y = y0 + self.fall_v * dt + 0.5 * self.air_g * dt * dt  # conta exata: o arco chega à altura calculada
            self.fall_v += self.air_g * dt
            if self.air_vx:
                a = self.area()
                self.foot.setX(min(max(self.foot.x() + self.air_vx * dt, a.left()), a.right()))
            surf = self._landing(self.foot.x(), y0, y) if self.fall_v > 0 else None
            if surf is not None:
                self._land(soft=self.flight == "pulo", surf=surf)
            else:
                self.foot.setY(y)
        if self.vel:
            x = self.foot.x() + self.vel * dt
            if self.walk_target is not None:
                if (self.vel > 0 and x >= self.walk_target) or (self.vel < 0 and x <= self.walk_target):
                    x = self.walk_target
                    self.walk_target = None
                    self.vel = 0
                    done, self._walk_done = getattr(self, "_walk_done", None), None
                    # chegou: vai direto para o quadro de parar (sem andar no lugar)
                    if self.player.aid == "caminhar":
                        if done:
                            self.player._done = done
                        self.player.exit_core()
                    elif done:
                        done()
                    self.save_pos()
            elif not self.exiting and self.player.aid != "escondendo":
                x = self.clamp_x(x)
            self.foot.setX(x)
        self._place()
        if not self.vel and self.fall_v is None:
            self.move_timer.stop()

    # ---------- em cima das janelas: pulo, queda e acompanhar ----------
    def _landing(self, x, y0, y1):
        """Onde ela toca descendo de y0 até y1: a primeira borda de janela cruzada embaixo dos pés, ou "chao"."""
        m = 20 * self.sprites.scale
        hits = [sf for sf in self.surfaces if y0 <= sf.y <= y1 and sf.x0 + m <= x <= sf.x1 - m]
        if hits:
            return min(hits, key=lambda sf: sf.y)
        sc = QGuiApplication.screenAt(QPoint(int(x), int(min(y0, y1)))) or self.screen() \
            or QGuiApplication.primaryScreen()
        return "chao" if y1 >= sc.availableGeometry().bottom() + 1 else None

    def _surfaces(self, min_width=60, skip=None):
        """Onde dá para pousar: bordas de cima das janelas e os itens (botões, imagens...) da página da frente."""
        out = desktop.surfaces(min_width=min_width, top_margin=self.sit_room())
        h = self.page.hwnd if self.page else None  # última página lida (pegar a Ceci no mouse tira o navegador da frente)
        r = desktop.rect_of(h) if h else None
        if r is not None:
            wins = desktop.windows()
            out += [sf for sf in self.page.surfaces(h, min_width, self.area().top() + self.sit_room())
                    if r.top() < sf.y < r.bottom() - 8 and not self._covered(h, (sf.x0 + sf.x1) / 2, sf.y + 2, wins)]
        return [sf for sf in out if sf != skip]

    def _covered(self, hwnd, x, y, wins=None):
        """Alguma janela na frente da janela hwnd tapa o ponto (x, y)?"""
        for w in desktop.windows() if wins is None else wins:
            if w.hwnd == hwnd:
                return False
            if w.rect.contains(int(x), int(y)):
                return True
        return False

    def _set_perch(self, surf):
        self.perch = surf
        if self.page:
            self.page.track = surf.hwnd if surf and surf.el else None
            self.perch_gen = self.page.gen
        if surf:
            self.perch_rect = desktop.rect_of(surf.hwnd)
            self.perch_t = self.perch_check = time.monotonic()
            self.perch_timer.start(PERCH_MS)
        else:
            self.perch_rect = None
            self.perch_timer.stop()

    def _fly(self, vy, vx, kind, g=FALL_G, surfaces=None):
        """Sai do chão (ou da janela): fica na pose de queda da arrastada até tocar em algo."""
        self.walk_target, self.vel, self.spun = None, 0.0, False
        self.surfaces = self._surfaces() if surfaces is None else surfaces
        self.fall_v, self.air_vx, self.air_g, self.flight = vy, vx, g, kind
        self.play("arrastada", force=True, cut=True, start=self.sprites.anims["arrastada"]["fall"])
        self._start_move()

    def jump_to(self, surf, x, then=None):
        """Pulo com gravidade até a borda de cima de uma janela (surf) ou até o chão (surf=None), caindo em x."""
        if self.dragging or self.fall_v is not None or self.exiting:
            return False
        s = self.sprites.scale
        if surf is not None:
            m = 40 * s
            x, ty = min(max(x, surf.x0 + m), surf.x1 - m), surf.y
        else:
            a = self.area()
            x, ty = min(max(x, a.left() + 45 * s), a.right() - 45 * s), a.bottom() + 1
        up = self.foot.y() - ty            # quanto o alvo está acima dos pés (negativo: embaixo)
        rise = max(up, 0) + max(45 * s, 24)  # o arco passa um pouco acima do alvo
        v0 = math.sqrt(2 * JUMP_G * rise)
        t = v0 / JUMP_G + math.sqrt(2 * (rise - up) / JUMP_G)
        self._set_perch(None)
        self.after_land = then
        self._fly(-v0, (x - self.foot.x()) / t, "pulo", JUMP_G, [surf] if surf else [])
        return True

    def climb(self):
        """Sobe sozinha na borda de cima de uma janela à vista (de preferência a da frente): anda até perto
        e pula. False quando não tem borda livre ao alcance."""
        if self.perch or self.dragging or self.fall_v is not None or self.exiting:
            return False
        s, g = self.sprites.scale, self.ground()
        opts = [sf for sf in self._surfaces(min_width=int(90 * s))
                if self.headroom() * 0.5 <= g - sf.y <= MAX_JUMP * s and (sf.el or sf.x1 - sf.x0 >= 150 * s)]
        if not opts:
            return False
        fg = desktop.foreground()
        items = [sf for sf in opts if sf.el]  # botões, imagens... da página: o mais divertido
        front = [sf for sf in opts if fg and sf.hwnd == fg.hwnd and not sf.el]
        pick = random.choice(items if items and random.random() < 0.7 else (front or opts))
        tx = min(max(self.foot.x(), pick.x0 + 60 * s), pick.x1 - 60 * s)
        side = -1 if tx < self.foot.x() else 1
        launch = self.clamp_x(tx - side * 70 * s)  # toma impulso de lado, não pula reto para cima

        def go():
            sf = self.page.find(pick, tx) if pick.el and self.page else desktop.surface_at(pick.hwnd, tx)
            if sf and not self.dragging and not self.perch and self.headroom() * 0.5 <= self.ground() - sf.y \
                    <= MAX_JUMP * s and sf.y >= self.area().top() + self.sit_room():
                self.jump_to(sf, tx)
        self.walk_to(launch, on_done=go)
        return True

    def drop(self):
        """A borda embaixo dela sumiu (janela fechou, minimizou, maximizou ou foi coberta): cai até o que tiver
        embaixo (outra janela ou o chão)."""
        if not self.perch or self.dragging or self.exiting:
            return
        old = self.perch
        self._set_perch(None)
        self.interaction.emit("caiu")
        self._fly(0.0, 0.0, "queda", surfaces=[sf for sf in self._surfaces()
                                               if (sf.el != old.el if old.el else sf.hwnd != old.hwnd)])

    def _perch_tick(self):
        """Sentada numa janela: vai junto quando você arrasta a janela; cai se ela some, minimiza, maximiza,
        sobe demais ou fica coberta por outra."""
        p = self.perch
        if not p or self.dragging or self.fall_v is not None:
            return
        r = desktop.rect_of(p.hwnd)
        if r is None or not p.el and (desktop.is_maximized(p.hwnd) or r.top() < self.area().top() + self.sit_room()):
            return self.drop()
        old, now = self.perch_rect, time.monotonic()
        if old is not None and (r.left() != old.left() or r.top() != old.top()):
            dx, dy = r.left() - old.left(), r.top() - old.top()
            self.perch = p = replace(p, y=p.y + dy, x0=p.x0 + dx, x1=p.x1 + dx)
            self.foot += QPointF(dx, dy)
            if self.walk_target is not None:
                self.walk_target += dx
            self._place()
        if self.low() and self.player.aid == "borda" and now > getattr(self, "low_until", now + 1):
            return self.jump_to(None, self.foot.x())  # cansou de ficar sentada lá em cima: desce
        resized = old is not None and r.size() != old.size()
        self.perch_rect = r
        if p.el:  # num botão/imagem da página: segue quando a página rola; cai quando o item some ou é tapado
            if now - self.perch_check < 0.2 or not self.page or not self.page.fresh(p.hwnd):
                return
            self.perch_check = now
            if self.page.gen != getattr(self, "perch_gen", self.page.gen):
                return self.drop()  # trocou de aba/página: o botão onde ela estava não existe mais
            sf = self.page.find(p, self.foot.x(), max_dy=max(260 * self.sprites.scale, 120))
            if sf is None or self._covered(p.hwnd, self.foot.x(), sf.y + 2) \
                    or sf.y < self.area().top() + self.sit_room() or not r.top() < sf.y < r.bottom() - 8:
                return self.drop()
            if sf.y != p.y:
                self.foot += QPointF(0, sf.y - p.y)
                self._place()
            self.perch = sf
            if self.walk_target is not None:
                self.walk_target = self.clamp_x(self.walk_target)
            return
        if resized or now - self.perch_check >= PERCH_CHECK:
            self.perch_check = now
            sf = desktop.surface_at(p.hwnd, self.foot.x())
            if sf is None:
                return self.drop()
            self.perch = sf
            if self.walk_target is not None:
                self.walk_target = self.clamp_x(self.walk_target)

    # ---------- olhos seguindo o mouse ----------
    def update_eye_timer(self):
        on = self.settings["follow_mouse"] and self.isVisible() and not self.player.paused
        if on and not self.eye_timer.isActive():
            self.eye_timer.start(150 if not self.settings["eco"] else 300)
        elif not on:
            self.eye_timer.stop()
            self.eyes_off()

    def _head(self):
        s = self.sprites.scale
        return self.foot + QPointF(0, -285 * s)

    def _eye_tick(self):
        if self.dragging or not (self.player.aid == "idle" or self.eyes_on):
            return
        if self.fall_v is not None or self.low():  # no ar ou sentada no teto baixo: olhar em pé não cabe
            return self.eyes_off()
        c = QCursor.pos()
        d = QPointF(c) - self._head()
        dist = math.hypot(d.x(), d.y())
        now = time.monotonic()
        s = self.sprites.scale
        # velocidade do cursor: só começa a seguir com o mouse mexendo bem rápido
        last, self.eye_last_pos = getattr(self, "eye_last_pos", None), (now, QPointF(c))
        speed = 0.0
        if last and now > last[0]:
            speed = math.hypot(c.x() - last[1].x(), c.y() - last[1].y()) / (now - last[0])
        if speed > 20:  # qualquer mexida (até devagar) conta: enquanto o mouse mexe ela não volta pro idle
            self.eye_last_move, self.eye_hold = now, None
        elif self.eyes_on and getattr(self, "eye_hold", None) is None:
            self.eye_hold = random.uniform(1.0, 3.0)  # mouse parou: ainda fica olhando 1 a 3 s
        if not self.eyes_on and (speed < 1800 or now - getattr(self, "eye_end_t", -99) < EYE_COOLDOWN):
            return
        if self.eyes_on and now - getattr(self, "eye_last_move", now) > (getattr(self, "eye_hold", None) or 3.0):
            self.eyes_off(back=True)  # mouse parado: volta ao idle
            return
        if self.eyes_on or dist < 420 * s * 1.6:  # começou a olhar: só para quando o mouse parar (longe ou perto)
            eyes = self.sprites.anims["seguir_mouse"]["eyes"]
            if dist < 45 * s:
                k = None  # cursor no rosto: mantém o olhar atual
            elif d.y() < -abs(d.x()) * 0.9:
                k = "up"
            elif d.y() > abs(d.x()) * 0.35:
                k = "down" if abs(d.x()) < d.y() * 0.4 else ("down_left" if d.x() < 0 else "down_right")
            elif d.x() < 0:
                k = "left"
            else:
                k = "right" if dist < 300 * s else "far_right"
            if k is None:
                return
            idx = tuple(eyes.get(k) or eyes["down_right"])
            if self.eyes_on and idx != self.eyes_idx and now - getattr(self, "eye_switch_t", 0) < EYE_HOLD:
                return  # segura a direção atual um pouco (não fica trocando a cada movimento)
            if idx != self.eyes_idx:
                self.eye_switch_t = now
                was = self.eyes_on
                self.eyes_on, self.eyes_idx = True, idx
                self._on_frame([idx[0], idx[1], 400], not was)
                if not was:
                    self.interaction.emit("olhando")

    def eyes_off(self, back=False):
        if self.eyes_on:
            self.eyes_on, self.eyes_idx = False, None
            self.eye_end_t = time.monotonic()
            if back and self.player.aid == "idle":
                self._on_frame(self.player.current["seq"][0], True)

    # ---------- mouse ----------
    def _hit(self, pos):
        f = self.cur
        if not f:
            return None
        x = pos.x() - (self.anchor.x() + f.ox)
        y = pos.y() - (self.anchor.y() + f.oy)
        if not (0 <= x < f.w and 0 <= y < f.h):
            return None
        img = f.pix.toImage()
        dpr = f.pix.devicePixelRatio()
        if img.pixelColor(int(x * dpr), int(y * dpr)).alpha() < 30:
            return None
        head_bottom = self.anchor.y() - 215 * self.sprites.scale
        return "head" if pos.y() < head_bottom else "body"

    def mousePressEvent(self, e):
        if self.exiting:
            return
        if e.button() == Qt.RightButton:
            self.context_menu.emit(e.globalPosition().toPoint())
            return
        if e.button() == Qt.LeftButton:
            self.pet_timer.stop()  # clique cancela o carinho que a mira acabou de "desenhar"
            self._reset_rub()
            self.press = (e.globalPosition(), self._hit(e.position()))
            self.press_t = time.monotonic()
            self.drag_off = self.foot - e.globalPosition()

    def mouseMoveEvent(self, e):
        if self.press and e.buttons() & Qt.LeftButton:
            gp = e.globalPosition()
            moved = (gp - self.press[0]).manhattanLength()
            held = time.monotonic() - self.press_t
            # clique com a mão tremendo (ou toque no touchpad) não levanta a Ceci: no começo do clique só um
            # puxão de verdade (DRAG_QUICK) vira arraste; segurando um pouco, basta mexer DRAG_START
            if not self.dragging and (moved > DRAG_QUICK or (held >= DRAG_HOLD and moved > DRAG_START)):
                self._start_drag()
            if self.dragging:
                self._drag_to(gp + self.drag_off)
            return
        # carinho: passar o mouse várias vezes pela cabeça (sem clicar)
        if self.settings["petting"] and self._hit(e.position()) == "head":
            self._rub(e.position())
        else:
            self.rub_last = None

    def _reset_rub(self):
        self.rub = {"x": [], "y": []}  # momentos em que o cursor mudou de sentido, por eixo
        self.rub_last = None
        self.rub_run = {"x": (0, 0.0), "y": (0, 0.0)}  # sentido e comprimento da passada atual

    def _rub(self, pos):
        """Conta as idas e vindas do cursor sobre a cabeça; PET_PASSES delas no mesmo eixo em PET_WINDOW s =
        carinho. Eixos separados: o caminho torto da mira até ela (um pouco em x, um pouco em y) não soma."""
        now = time.monotonic()
        last, self.rub_last = self.rub_last, QPointF(pos)
        for axis in self.rub:
            self.rub[axis] = [t for t in self.rub[axis] if now - t < PET_WINDOW]
        if last is None:
            return
        d = pos - last
        for axis, v in (("x", d.x()), ("y", d.y())):
            if not v:
                continue
            sgn = 1 if v > 0 else -1
            run_dir, run_len = self.rub_run[axis]
            if sgn == run_dir:
                run_len += abs(v)
            else:
                if run_len >= PET_STROKE * self.sprites.scale:
                    self.rub[axis].append(now)
                run_dir, run_len = sgn, abs(v)
            self.rub_run[axis] = (run_dir, run_len)
        if max(len(v) for v in self.rub.values()) >= PET_PASSES and not self.pet_timer.isActive():
            self._reset_rub()
            self.pet_timer.start(PET_CONFIRM)

    def mouseReleaseEvent(self, e):
        if e.button() != Qt.LeftButton or not self.press:
            return
        _, where = self.press
        self.press = None
        if self.dragging:
            self._end_drag()
            return
        if self.player.aid in ("cochilo", "dormindo"):
            self.wake()
        elif where:  # clicar nela (cabeça ou corpo) = Interagir; carinho é passando o mouse na cabeça
            self.click_timer.start()

    def _click(self):
        if not self.exiting and not self.dragging:
            aid, cat = self.mood.react("clique", self.player.aid, time.monotonic())
            self.interaction.emit(cat)
            self._react(aid)

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls() and not self.exiting:
            e.acceptProposedAction()

    def dropEvent(self, e):
        paths = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        if paths:
            e.acceptProposedAction()
            self.files_dropped.emit(paths)

    def mouseDoubleClickEvent(self, e):
        if e.button() != Qt.LeftButton or self.exiting or not self._hit(e.position()):
            return
        self.click_timer.stop()
        self.press = None  # o soltar do segundo clique não conta como clique
        self.double_clicked.emit()

    def interact(self, talk=False):
        """Menu/atalho Interagir: reage conforme o humor (feliz, fofa, apaixonadinha... ou brava)."""
        self._react(self.mood.react("clique", self.player.aid, time.monotonic())[0], talk)

    def _react(self, aid, talk=False):
        self.stop_walk()
        if self.low():  # em cima do vídeo flutuante não cabe em pé: só sentada
            return self.sit_low()
        self.play(aid, force=True, talk=talk)

    def pet(self):
        now = time.monotonic()
        if now - self.last_pet < 3.5 or self.player.aid in ("arrastada", "saida", "entrada"):
            return
        self.last_pet = now
        aid, cat = self.mood.react("carinho", self.player.aid, now)  # gostou, derreteu... ou enjoou e ficou brava
        self.interaction.emit(cat)
        self._react(aid)

    def wake(self):
        if self.player.aid in ("cochilo", "dormindo"):
            self.mood.woken(time.monotonic())  # acordada: fica mal-humorada uns segundos
            self.interaction.emit("acordando")
            self.player.exit_core()  # acorda e levanta com os quadros do próprio sheet (sem pular de pose)

    def _start_drag(self):
        self.dragging, self.lifted = True, False
        self.spin_pts, self.spun, self.spun_t = [], False, -99.0
        self.walk_target, self.vel, self.fall_v = None, 0.0, None
        self.air_vx, self.flight, self.after_land = 0.0, None, None
        self._set_perch(None)
        self.prev = None
        self.interaction.emit("arrastada")
        self.play("arrastada", force=True, cut=True)
        self.grabMouse()

    def _drag_to(self, p):
        vg = QRect()
        for sc in QGuiApplication.screens():
            vg = vg.united(sc.availableGeometry())
        s = self.sprites.scale
        x = min(max(p.x(), vg.left() + 40 * s), vg.right() - 40 * s)
        y = min(max(p.y(), vg.top() + 330 * s), vg.bottom() + 1)
        self.foot = QPointF(x, y)
        self._spin_check(p)
        g = self.ground()
        if y < g - 40 * s:
            self.lifted = True
        if self.lifted and y >= g - 2:
            # encostou na borda de baixo: pousa na hora (último quadro) e larga o arraste
            self.press = None
            self.releaseMouse()
            self.dragging = False
            self._land(soft=True)
            return
        self._place()

    def _spin_check(self, p):
        """Girando (ou sacudindo) no ar: muito caminho e muita curva em pouco tempo, não só arrastar reto."""
        now = time.monotonic()
        self.spin_pts = [(t, q) for t, q in self.spin_pts if now - t < SPIN_WINDOW] + [(now, QPointF(p))]
        if now - self.spun_t < SPIN_AGAIN:
            return
        path = turn = 0.0
        last = prev = None
        for _, q in self.spin_pts:
            if last is not None:
                d = q - last
                n = math.hypot(d.x(), d.y())
                if n < 3:  # tremidinha do mouse não conta
                    continue
                ang = math.atan2(d.y(), d.x())
                if prev is not None:
                    turn += abs((ang - prev + math.pi) % (2 * math.pi) - math.pi)
                path, prev = path + n, ang
            last = q
        if path > SPIN_PATH and turn > SPIN_TURN:
            self.spun, self.spun_t = True, now
            self.interaction.emit("girando")

    def _end_drag(self):
        self.releaseMouse()
        self.dragging = False
        a = self.player.current
        if self.foot.y() < self.ground() - 2 and a and a.get("fall") is not None:
            # solta no ar: cai até a borda de uma janela embaixo dela ou até o chão
            self.surfaces = self._surfaces()
            s, x, y = self.sprites.scale, self.foot.x(), self.foot.y()
            snap = [sf for sf in self.surfaces if abs(sf.y - y) <= max(40 * s, 30) and sf.x0 + 20 * s <= x <= sf.x1 - 20 * s]
            if snap:  # soltou com os pés um pouco abaixo da borda (no meio do botão): encaixa em cima dele
                sf = min(snap, key=lambda sf: abs(sf.y - y))
                self.foot.setY(sf.y)
                self.flight = None
                self._land(soft=True, surf=sf)
                return
            self.fall_v, self.air_vx, self.air_g, self.flight = 0.0, 0.0, FALL_G, None
            self.player.jump(a["fall"])  # caindo, segura até tocar em algo
            self._start_move()
        else:
            self._land(soft=True)

    def _land(self, soft, surf=None):
        """Tocou o chão ou a borda de uma janela: suave (arrastada até a borda, pulo) → último quadro;
        queda → impacto e recupera."""
        flight, then = self.flight, self.after_land
        self.fall_v, self.air_vx, self.air_g, self.flight, self.after_land = None, 0.0, FALL_G, None, None
        self._set_perch(surf if isinstance(surf, desktop.Surface) else None)
        self.foot.setY(self.ground())
        self._place()
        self.save_pos()
        a = self.player.current
        if self.player.aid == "arrastada" and a:
            if flight is None:  # pulo e queda já falaram (ou não precisam): solta/tonta é do arraste
                self.interaction.emit("tonta" if getattr(self, "spun", False) else "solta")
            self.player.jump(len(a["seq"]) - 1 if soft else a.get("land", len(a["seq"]) - 1))
        if self.perch and flight != "queda":
            self.interaction.emit("janela")
        if self.low():  # teto baixo: senta na hora
            QTimer.singleShot(500, self.sit_low)
        if then:
            QTimer.singleShot(700, then)

    # ---------- visibilidade ----------
    def suspend(self, on):
        """Oculta/pausa: nenhum timer fica rodando."""
        self.player.set_paused(on)
        for t in (self.move_timer, self.fade_timer, self.perch_timer):
            t.stop()
        if not on and self.perch:
            self.perch_timer.start(PERCH_MS)
        self.update_eye_timer()
        self.update_breath()
