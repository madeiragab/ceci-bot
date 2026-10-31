"""Clique nela (cabeça ou corpo) = Interagir com fala de clique; carinho só passando o mouse várias vezes
pela cabeça; sentada na borda fica na beirada da barra de tarefas; não abre duas Cecis.

Uso: python tests/interact_test.py
"""
import os
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["CECI_CONFIG_DIR"] = tempfile.mkdtemp(prefix="cecibot_test_")  # nunca as do usuário
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import QPointF, Qt, QTimer  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import main as M  # noqa: E402
from ceci.window import CANVAS_H, INTERACT, PET_PASSES  # noqa: E402

qa = QApplication(sys.argv)
fails = []


def check(name, cond):
    print(("ok   " if cond else "FALHA"), name)
    if not cond:
        fails.append(name)


app = M.App(qa)
app.s["follow_mouse"] = False
w, sp = app.win, app.speech
w.set_start_pos()
w.show()
w.play("idle", force=True)
s = w.sprites.scale
head = w.anchor + QPointF(0, -290 * s)
body = w.anchor + QPointF(0, -110 * s)


def click(pos):
    sp.hide()
    w.play("idle", force=True, cut=True)
    QTest.mouseClick(w, Qt.LeftButton, Qt.NoModifier, pos.toPoint())


def step1():
    check("ponto da cabeça é cabeça e o do corpo é corpo", w._hit(head) == "head" and w._hit(body) == "body")
    click(body)
    check("clique no corpo = Interagir", w.player.aid in INTERACT)
    check("clique fala uma frase de clique", sp.bubble.cat == "clique")
    click(head)
    check("clique na cabeça também = Interagir (não é carinho)", w.player.aid in INTERACT
          and w.player.aid != "carinho")
    QTimer.singleShot(200, step2)


def rub(points):
    w.rub_last = None
    for p in points:
        w._rub(p)


def step2():
    w.play("idle", force=True, cut=True)
    w.last_pet = 0.0
    rub([head + QPointF(-30 * s + 6 * s * k, 0) for k in range(11)])  # uma passada só, sem voltar
    check("uma passada só não é carinho", w.player.aid != "carinho")
    zig = []
    for n in range(PET_PASSES + 2):  # vai e volta várias vezes sobre a cabeça
        xs = range(11) if n % 2 == 0 else range(10, -1, -1)
        zig += [head + QPointF(-30 * s + 6 * s * k, 0) for k in xs]
    rub(zig)
    check("passar o mouse várias vezes pela cabeça = carinho", w.player.aid == "carinho")
    QTimer.singleShot(200, step3)


def step3():
    w.play("borda", force=True, cut=True)
    w.player.jump(4)
    f, g = w.cur, w.ground()
    bottom = w.foot.y() + f.oy + f.h
    check("sentada na borda: pernas descem por cima da barra (abaixo do chão)", bottom > g + 40 * s)
    check("e cabem na janela (nada cortado)", bottom <= w.y() + CANVAS_H * s)
    check("assento na linha do chão (±12 px na arte)", abs(bottom - 67 * w.sprites.scale - g) < 12 * s)
    if sys.platform == "win32":
        check("primeira Ceci abre", not M.already_running())
        check("segunda Ceci não abre", M.already_running())
    qa.exit(1 if fails else 0)


QTimer.singleShot(300, step1)
QTimer.singleShot(20000, lambda: (print("timeout"), qa.exit(2)))
sys.exit(qa.exec())
