"""Seguir o mouse: começa com o mouse mexendo rápido perto dela; depois de começar só para 1 a 3 s depois
que o mouse parar (mesmo que ele vá pra longe); não olha em pé no ar.

Uso: python tests/eyes_test.py
"""
import os
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["CECI_CONFIG_DIR"] = tempfile.mkdtemp(prefix="cecibot_test_")  # nunca as do usuário
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import QPoint  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import main as M  # noqa: E402
M.fullscreen_app_active = lambda: False
import ceci.window as W  # noqa: E402

qa = QApplication(sys.argv)
fails = []


def check(name, cond):
    print(("ok   " if cond else "FALHA"), name)
    if not cond:
        fails.append(name)


now = [1000.0]
cur = [QPoint(0, 0)]
class FakeTime:  # relógio e cursor falsos (só no módulo da janela)
    @staticmethod
    def monotonic():
        return now[0]


W.time = FakeTime


class FakeCursor:
    @staticmethod
    def pos():
        return cur[0]


W.QCursor = FakeCursor
app = M.App(qa)
app.beh.stop()
w = app.win
w.set_start_pos()
w.show()
w.play("idle", force=True)
h = w._head().toPoint()


def move(to, secs=0.15):
    now[0] += secs
    cur[0] = to
    w._eye_tick()


move(h + QPoint(300, 0))
move(h + QPoint(30, 0))  # passou rápido perto da cabeça
check("mouse rápido perto: começa a olhar", w.eyes_on)
for i in range(30):  # 4,5 s mexendo, bem longe dela
    move(h + QPoint(-1500 - (i % 2) * 200, 600))
check("mouse longe mas mexendo: continua olhando", w.eyes_on)
check("longe à esquerda/embaixo: olha pra esse lado", w.eyes_idx == tuple(w.sprites.anims["seguir_mouse"]["eyes"]["down_left"]))
for i in range(40):  # 6 s mexendo devagar (5 px por vez)
    move(cur[0] + QPoint(5, 0))
check("mouse mexendo devagar: não volta pro idle", w.eyes_on)
for _ in range(6):  # 0,9 s parado
    move(cur[0])
check("parado há menos de 1 s: ainda olhando", w.eyes_on)
check("tempo olhando depois de parar sorteado entre 1 e 3 s", 1.0 <= w.eye_hold <= 3.0)
move(cur[0] + QPoint(40, 0))  # mexeu de novo
for _ in range(6):
    move(cur[0])
check("mexeu de novo: continua acompanhando (o tempo recomeça)", w.eyes_on)
for _ in range(15):  # mais 2,25 s: passou de 3 s parado
    move(cur[0])
check("mouse parado mais de 3 s: para de olhar e volta ao idle", not w.eyes_on and w.player.aid == "idle")

now[0] += 10
move(h + QPoint(400, 0))
move(h + QPoint(30, 0))
check("de novo: começa a olhar", w.eyes_on)
w.fall_v = 100.0
move(h + QPoint(200, 0))
check("no ar: para de olhar", not w.eyes_on)
w.fall_v = None

print("\n" + ("tudo certo" if not fails else f"{len(fails)} FALHA(S): {fails}"))
os._exit(1 if fails else 0)
