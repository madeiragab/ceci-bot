"""Janela transparente da Ceci: desenho, posição, movimento e interações com o mouse."""
import math
import random
import time

from PySide6.QtCore import QPoint, QPointF, QRect, Qt, QTimer, Signal
from PySide6.QtGui import QCursor, QGuiApplication, QPainter
from PySide6.QtWidgets import QWidget

from .engine import Player
from .sprites import Sprites

CANVAS_W, CANVAS_H, FOOT_MARGIN = 640, 590, 100  # em px de sprite (escala 1.0); margem: pernas na barra
DRAG_START, DRAG_QUICK, DRAG_HOLD = 6, 22, 0.25  # px parado/segurando; px num clique rápido; s até "segurar"
INTERACT = ("acenando", "feliz", "beijinho", "coracao", "fofa")  # clique ou menu Interagir
PET_PASSES, PET_STROKE, PET_WINDOW = 5, 30, 3.0  # carinho: 5 idas e vindas (≥ 30 px) no MESMO eixo em 3 s
PET_CONFIRM = 450  # ms: clicou logo depois? era só a mira chegando nela — vale o clique, não o carinho
SPIN_WINDOW, SPIN_PATH, SPIN_TURN = 1.5, 500, 3 * math.pi  # girada/sacudida: 1,5 volta (ou 3 idas e vindas)
SPIN_AGAIN = 6.0  # s até poder reclamar de novo se continuar girando
EYE_HOLD = 1.5       # s mínimos olhando numa direção antes de trocar
EYE_COOLDOWN = 10.0  # s depois de parar de olhar o mouse até poder começar de novo
FADE_MS = 420  # troca de animação: desenhos diferentes precisam de um dissolve mais longo


class CeciWindow(QWidget):
    context_menu = Signal(QPoint)
    became_idle = Signal()
    moved = Signal()
    interaction = Signal(str)  # clique, carinho, arrastada, girando, solta, tonta, acordando, olhando (falas)

    def __init__(self, settings):
        super().__init__(None)
        self.settings = settings
        self._apply_flags()
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setMouseTracking(True)
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
        self.fall_v = None          # queda após soltar o arraste
        self.last_move = time.monotonic()
        self.move_timer = QTimer(self, timeout=self._move_tick)

        self.press, self.press_t = None, 0.0
        self.dragging = False
        self.drag_off = QPointF()
        self._reset_rub()
        self.last_pet = 0.0
        self.pet_timer = QTimer(self, singleShot=True, timeout=self.pet)
        self.eyes_on = False
        self.eyes_idx = None
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
        return self.area().bottom() + 1

    def clamp_x(self, x, margin=None):
        a = self.area()
        m = 45 * self.sprites.scale if margin is None else margin
        return min(max(x, a.left() + m), a.right() - m)

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
            self.fall_v += 2600 * dt
            y = self.foot.y() + self.fall_v * dt
            g = self.ground()
            if y >= g:
                y, self.fall_v = g, None
                self.foot.setY(y)
                self._land(soft=False)
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
        if speed > 120:
            self.eye_last_move = now
        if not self.eyes_on and (speed < 1800 or now - getattr(self, "eye_end_t", -99) < EYE_COOLDOWN):
            return
        if self.eyes_on and now - getattr(self, "eye_last_move", now) > 2.0:
            self.eyes_off(back=True)  # mouse parado: volta ao idle
            return
        if dist < 420 * s * 1.6:
            self.eyes_last_near = now
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
        elif self.eyes_on and now - self.eyes_last_near > 1.2:
            self.eyes_off(back=True)

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
            self.interaction.emit("clique")
            self.interact()

    def interact(self, talk=False):
        self.stop_walk()
        self.play(random.choice(INTERACT), force=True, talk=talk)

    def pet(self):
        now = time.monotonic()
        if now - self.last_pet < 3.5 or self.player.aid in ("carinho", "arrastada", "saida", "entrada"):
            return
        self.last_pet = now
        self.stop_walk()
        self.interaction.emit("carinho")
        self.play("carinho", force=True)

    def wake(self):
        if self.player.aid in ("cochilo", "dormindo"):
            self.interaction.emit("acordando")
            self.player.exit_core()  # acorda e levanta com os quadros do próprio sheet (sem pular de pose)

    def _start_drag(self):
        self.dragging, self.lifted = True, False
        self.spin_pts, self.spun, self.spun_t = [], False, -99.0
        self.walk_target, self.vel, self.fall_v = None, 0.0, None
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
            self.fall_v = 0.0
            self.player.jump(a["fall"])  # caindo, segura até tocar o chão
            self._start_move()
        else:
            self._land(soft=True)

    def _land(self, soft):
        """Tocou o chão: suave (arrastada até a borda) → último quadro; queda → impacto e recupera."""
        self.fall_v = None
        self.foot.setY(self.ground())
        self._place()
        self.save_pos()
        a = self.player.current
        if self.player.aid == "arrastada" and a:
            self.interaction.emit("tonta" if getattr(self, "spun", False) else "solta")
            self.player.jump(len(a["seq"]) - 1 if soft else a.get("land", len(a["seq"]) - 1))

    # ---------- visibilidade ----------
    def suspend(self, on):
        """Oculta/pausa: nenhum timer fica rodando."""
        self.player.set_paused(on)
        for t in (self.move_timer, self.fade_timer):
            t.stop()
        self.update_eye_timer()
        self.update_breath()
