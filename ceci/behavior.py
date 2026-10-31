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
        win.became_idle.connect(self.schedule)

    def schedule(self):
        if self.win.player.paused or not self.win.isVisible():
            return
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
        aid = self._choose()
        if aid == "_walk":
            # só anda para um lado que tenha espaço de verdade (nunca "contra" a borda)
            a, s = w.area(), w.sprites.scale
            margin, want = 110 * s, random.uniform(130, 400) * s
            room = {-1: w.foot.x() - (a.left() + margin), 1: (a.right() - margin) - w.foot.x()}
            sides = [d for d, r in room.items() if r >= 90 * s]
            if not sides:
                self.schedule()
                return
            d = random.choices(sides, weights=[room[x] for x in sides])[0]
            w.walk_to(w.foot.x() + d * min(want, room[d]))
            return
        if aid == "escondendo":
            r = w.area().right() + 1
            s = w.sprites.scale
            if w.foot.x() > r - 260 * s:
                # já perto da borda direita: não anda para o lado, só agacha e se esconde
                w.play("escondendo", force=True, start=4)
            else:
                w.walk_to(r - 230 * s, on_done=lambda: w.play("escondendo", force=True))
        else:
            w.play(aid)
        self.recent = (self.recent + [aid])[-4:]
        if w.sprites.anims.get(aid, {}).get("special"):
            self.last_special = time.monotonic()

    def _choose(self):
        anims = self.win.sprites.anims
        idle_for = time.monotonic() - self.last_user
        pool = {}
        for aid, a in anims.items():
            wgt = a.get("auto", 0)
            if not wgt or aid in self.recent:
                continue
            if a.get("special"):
                if not self.s["specials"] or time.monotonic() - self.last_special < SPECIAL_COOLDOWN:
                    continue
            pool[aid] = wgt
        if self.s["walk"]:
            pool["_walk"] = 8
        # cansaço: depois de muito tempo sem interação, cochilo fica mais provável
        if "cochilo" not in self.recent:
            pool["cochilo"] = 2 + (12 if idle_for > 600 else 0)
        if self.s["specials"] and time.monotonic() - self.last_special > SPECIAL_COOLDOWN:
            pool["escondendo"] = 1
        # a maior parte do tempo: micro-animações discretas
        for m in MICRO:
            if m in pool:
                pool[m] *= 2
        keys = list(pool)
        return random.choices(keys, weights=[pool[k] for k in keys])[0]

    def user_activity(self):
        self.last_user = time.monotonic()
