"""Rotina automática: decide o que a Ceci faz quando está ociosa (sem IA, só timers e pesos)."""
import random
import time

from PySide6.QtCore import QObject, QTimer

MICRO = ("ajeitando", "idle_fofo", "curiosa")
SPECIAL_COOLDOWN = 300  # s entre animações especiais


class Behavior(QObject):
    def __init__(self, win, settings):
        super().__init__()
        self.win, self.s = win, settings
        self.timer = QTimer(self, singleShot=True, timeout=self._tick)
        self.recent = []
        self.last_special = time.monotonic()
        self.last_user = time.monotonic()
        self.mind = None  # cérebro (ceci/ia/live.py): o que ela tá com vontade de fazer fica mais provável
        win.became_idle.connect(self.schedule)

    def schedule(self):
        if self.win.player.paused or not self.win.isVisible():
            return
        if self.win.low():  # colada no topo da tela: não fica em pé com a cabeça pra fora
            return self.timer.start(400)
        base = random.uniform(5, 16) / max(0.2, self.s["random_freq"])
        if self.s["eco"]:
            base *= 2
        self.timer.start(int(base * 1000))

    def stop(self):
        self.timer.stop()

    def _tick(self):
        w = self.win
        if not w.is_idle() or w.player.paused:
            if w.eyes_on:  # olhando o mouse: tenta depois
                self.schedule()
            return
        if w.low():  # em cima do vídeo flutuante (teto baixo): só sentada (a janela decide quando desce)
            w.sit_low()
            return
        aid = self._choose()
        if aid in ("_subir", "_descer"):
            self.recent = (self.recent + [aid])[-4:]
        if aid == "_subir":  # pula para a borda de cima de uma janela à vista
            if not w.climb():
                self.schedule()
            return
        if aid == "_descer":
            w.jump_to(None, w.foot.x() + random.choice((-1, 1)) * random.uniform(40, 140) * w.sprites.scale)
            return
        if aid == "_walk":
            # só anda para um lado que tenha espaço de verdade (nunca "contra" a borda da tela ou da janela)
            (left, right), s = w.span(), w.sprites.scale
            margin, want = (40 if w.perch else 110) * s, random.uniform(130, 400) * s
            room = {-1: w.foot.x() - (left + margin), 1: (right - margin) - w.foot.x()}
            sides = [d for d, r in room.items() if r >= (30 if w.perch else 90) * s]
            if not sides:
                self.schedule()
                return
            d = random.choices(sides, weights=[room[x] for x in sides])[0]
            w.walk_to(w.foot.x() + d * min(want, room[d]))
            return
        w.play(aid)  # animações presas à parede (esconder) andam até a borda sozinhas antes
        self.recent = (self.recent + [aid])[-4:]
        if w.sprites.anims.get(aid, {}).get("special"):
            self.last_special = time.monotonic()

    def _choose(self):
        anims = self.win.sprites.anims
        idle_for = time.monotonic() - self.last_user
        perched = self.win.perch is not None
        pool = {}
        for aid, a in anims.items():
            wgt = a.get("auto", 0)
            if not wgt or aid in self.recent or (perched and a.get("edge")):
                continue
            if perched and aid == "borda":
                wgt *= 4  # em cima da janela: sentar com as pernas balançando na borda
            if a.get("special"):
                if not self.s["specials"] or time.monotonic() - self.last_special < SPECIAL_COOLDOWN:
                    continue
            pool[aid] = wgt
        if self.s["walk"]:
            pool["_walk"] = 8
        # cansaço: depois de muito tempo sem interação, cochilo fica mais provável
        if "cochilo" not in self.recent:
            pool["cochilo"] = 2 + (12 if idle_for > 600 else 0)
        if self.s["specials"] and time.monotonic() - self.last_special > SPECIAL_COOLDOWN and not perched:
            pool["escondendo"] = 1
        if self.s.get("perch", True):
            if perched:
                up = time.monotonic() - self.win.perch_t
                if up > 40:
                    pool["_descer"] = 2 + (5 if up > 240 else 0)
            elif "_subir" not in self.recent and "_descer" not in self.recent:
                pool["_subir"] = 3
        # a maior parte do tempo: micro-animações discretas
        for m in MICRO:
            if m in pool:
                pool[m] *= 2
        if self.mind:
            pool = {k: v * self.mind.boost(k) for k, v in pool.items()}
        keys = list(pool)
        return random.choices(keys, weights=[pool[k] for k in keys])[0]

    def user_activity(self):
        self.last_user = time.monotonic()
