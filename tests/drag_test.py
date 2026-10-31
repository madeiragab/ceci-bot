"""Arraste: encostar na borda de baixo pousa no último quadro; soltar no ar segura "caindo" e,
ao tocar o chão, vai direto ao impacto.

Uso: python tests/drag_test.py
"""
import os
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["CECI_CONFIG_DIR"] = tempfile.mkdtemp(prefix="cecibot_test_")  # nunca as do usuário
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import QPointF, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from ceci.settings import Settings  # noqa: E402
from ceci.window import CeciWindow  # noqa: E402

app = QApplication(sys.argv)
s = Settings()
s.save = lambda: None  # não mexe na posição salva do usuário
s["follow_mouse"] = False
win = CeciWindow(s)
win.set_start_pos()
win.show()
a = win.sprites.anims["arrastada"]
last = len(a["seq"]) - 1
fails = []


def check(name, cond):
    print(("ok   " if cond else "FALHA"), name)
    if not cond:
        fails.append(name)


def lift():
    win._start_drag()
    g = win.ground()
    win._drag_to(QPointF(win.foot.x(), g - 200))


def t1():
    lift()
    check("levantada: susto -> pendurada (antes do final)", win.player.i <= a["loop"][1])
    win._drag_to(QPointF(win.foot.x(), win.ground() + 50))  # empurra até a borda de baixo
    check("encostou embaixo -> último quadro na hora", win.player.aid == "arrastada" and win.player.i == last)
    check("arraste encerrado e pés no chão", not win.dragging and abs(win.foot.y() - win.ground()) < 1)
    QTimer.singleShot(1500, t2)


def t2():
    lift()
    win._end_drag()  # solta no ar
    check("solta no ar -> quadro 'caindo'", win.player.i == a["fall"] and win.fall_v is not None)
    QTimer.singleShot(1200, t3)


def t3():
    check("tocou o chão -> impacto (ou depois dele)", win.fall_v is None and
          (win.player.aid != "arrastada" or win.player.i >= a["land"]))
    app.exit(1 if fails else 0)


QTimer.singleShot(200, t1)
QTimer.singleShot(8000, lambda: (print("timeout"), app.exit(2)))
sys.exit(app.exec())
