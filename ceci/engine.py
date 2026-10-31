"""Motor de animação por estados: início → miolo em loop → final.

Cada animação pode ter um trecho "loop" [i, j]. O miolo repete por um tempo ("hold": [min_s, max_s]),
um número de vezes ("loops") ou até alguém pedir para sair ("inf"). O final (passos depois de j) só
toca quando ela vai trocar de animação: pedir outra animação no meio do miolo agenda a troca para
depois do final (ex.: guarda o livro antes de receber carinho). Só um corte explícito (arraste) pula.

Um único QTimer de disparo único: quadro parado não gera trabalho.
"""
import random
import time

from PySide6.QtCore import QObject, QTimer, Signal


class Player(QObject):
    frame = Signal(object, bool)   # (passo [sheet, idx, ms, extras?], nova_animacao)
    finished = Signal(str)

    def __init__(self, anims, settings):
        super().__init__()
        self.anims = anims
        self.settings = settings
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self._advance)
        self.aid = None
        self.i = 0
        self.paused = False
        self.loop_override = None  # painel: True força repetir
        self.mirror = False
        self.pending = None
        self._done = None

    # --- consulta ---
    @property
    def current(self):
        return self.anims.get(self.aid) if self.aid else None

    def in_core(self):
        """Ainda antes do fim do miolo (há um final a tocar antes de trocar)?"""
        a = self.current
        return bool(a and a.get("loop") and self.i <= a["loop"][1])

    def can_play(self, aid):
        cur = self.current
        return cur is None or self.aid == "idle" or self.anims[aid]["prio"] >= cur["prio"]

    # --- controle ---
    def play(self, aid, loops=None, on_done=None, force=False, mirror=False, cut=False, start=0):
        if aid not in self.anims or (not force and not self.can_play(aid)):
            return False
        if not cut and aid != self.aid and self.aid != "idle" and self.in_core():
            self.pending = (aid, dict(loops=loops, on_done=on_done, mirror=mirror, start=start))
            self.exit_core()
            return True
        self._start(aid, loops, on_done, mirror, start)
        return True

    def _start(self, aid, loops, on_done, mirror, start):
        a = self.anims[aid]
        self.aid, self.i = aid, max(0, min(start, len(a["seq"]) - 1))
        self.mirror = bool(mirror and a.get("mirror", False))
        self.pending, self._done = None, on_done
        lp = loops if loops is not None else a.get("loops")
        if lp == "inf":
            self.loops_left = float("inf")
        elif isinstance(lp, list):
            self.loops_left = random.randint(lp[0], lp[1]) - 1
        else:
            self.loops_left = (lp or 1) - 1
        self.hold = a.get("hold") if loops is None else None
        self.deadline = None
        self._show(True)

    def exit_core(self, quick=True):
        """Sai do miolo agora e segue para o final da animação atual."""
        a = self.current
        if not a:
            return
        self.loops_left, self.hold, self.loop_override = 0, None, None
        lp = a.get("loop")
        if lp and self.i <= lp[1]:
            self.i = lp[1]  # o próximo passo é o primeiro do final
            if quick and not self.paused:
                self.timer.start(int(min(220, a["seq"][self.i][2]) / max(0.1, self.settings["speed"])))

    def jump(self, i):
        """Vai direto para o passo i da animação atual (ex.: pouso ao tocar o chão), sem repetir o miolo."""
        a = self.current
        if not a:
            return
        self.loops_left, self.hold, self.loop_override, self.deadline = 0, None, None, None
        self.timer.stop()
        self.i = max(0, min(i, len(a["seq"]) - 1))
        self._show(False)

    def stop(self, graceful=True):
        if not self.aid:
            return
        if graceful and self.in_core():
            self.exit_core()
        elif not graceful:
            self.finish()

    def finish(self):
        aid, done, pend = self.aid, self._done, self.pending
        self._done = self.pending = None
        self.timer.stop()
        self.finished.emit(aid or "")
        if pend:
            self._start(pend[0], pend[1]["loops"], pend[1]["on_done"], pend[1]["mirror"], pend[1]["start"])
            return
        if done:
            done()
        if self.aid == aid:  # ninguém trocou a animação
            nxt = self.anims.get(aid, {}).get("next", "idle")
            if nxt:
                self._start(nxt, None, None, False, 0)

    def set_paused(self, p):
        self.paused = p
        if p:
            self.timer.stop()
        elif self.aid:
            self._schedule()

    def step(self, d):
        """Avanço manual (painel). Pausa a reprodução."""
        if not self.aid:
            return
        self.set_paused(True)
        self.i = (self.i + d) % len(self.current["seq"])
        self._show(False)

    def restart(self):
        if self.aid:
            self._start(self.aid, None, None, self.mirror, 0)

    # --- interno ---
    def _show(self, new):
        a = self.current
        lp = a.get("loop")
        if lp and self.i == lp[0] and self.deadline is None and self.hold:
            self.deadline = time.monotonic() + random.uniform(*self.hold)
        self.frame.emit(a["seq"][self.i], new)
        if not self.paused:
            self._schedule()

    def _schedule(self):
        st = self.current["seq"][self.i]
        ms = st[2]
        if self.aid == "idle" and len(self.current["seq"]) == 1:
            ms = 60000  # idle parado: um timer longo basta
        elif len(st) > 3 and "rand" in st[3]:  # pausa natural variável num quadro
            ms = random.randint(st[3]["rand"][0], st[3]["rand"][1])
        self.timer.start(max(16, int(ms / max(0.1, self.settings["speed"]))))

    def _repeat(self):
        if self.loop_override:
            return True
        if self.loops_left > 0:
            self.loops_left -= 1
            return True
        return self.deadline is not None and time.monotonic() < self.deadline

    def _advance(self):
        a = self.current
        if a is None:
            return
        lp = a.get("loop")
        if lp and self.i == lp[1] and self._repeat():
            self.i = lp[0]
        elif self.i + 1 < len(a["seq"]):
            self.i += 1
        elif self.loop_override:
            self.i = 0
        else:
            self.finish()
            return
        self._show(False)
