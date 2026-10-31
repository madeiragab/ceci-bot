"""Girar (ou sacudir) a Ceci no ar tem falas próprias; arrastar reto não. Depois do giro, o pouso é tonta.

Uso: python tests/spin_test.py
"""
import math
import os
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["CECI_CONFIG_DIR"] = tempfile.mkdtemp(prefix="cecibot_test_")  # nunca as do usuário
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import QPointF, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import main as M  # noqa: E402
M.fullscreen_app_active = lambda: False  # tela cheia de verdade no PC (vídeo, jogo) não entra no teste

qa = QApplication(sys.argv)
fails = []


def check(name, cond):
    print(("ok   " if cond else "FALHA"), name)
    if not cond:
        fails.append(name)


app = M.App(qa)
app.s["follow_mouse"] = False
w, sp, b = app.win, app.speech, app.speech.bubble
app.start()
app.beh.stop()
said = []
_start = b.start
b.start = lambda text, cat, prio: (said.append(cat), _start(text, cat, prio))
a = w.area()
cx, cy = a.center().x(), a.top() + 420


def feed(points, then, i=0):
    if i < len(points):
        w._drag_to(QPointF(*points[i]))
        QTimer.singleShot(40, lambda: feed(points, then, i + 1))
    else:
        then()


def cats():
    return ([b.cat] if b.active() else []) + [q[0] for q in sp.queue]


def straight():
    sp.hide()
    said.clear()
    w._start_drag()
    feed([(cx - 300 + 15 * k, cy) for k in range(40)], straight_done)


def straight_done():
    check("arrastar reto não conta como giro", "girando" not in cats() and not w.spun)
    w._end_drag()
    QTimer.singleShot(9000, spin)


def spin():
    check("pouso normal fala de pouso", "solta" in said and "tonta" not in said)
    sp.hide()
    said.clear()
    w._start_drag()
    pts = [(cx + 90 * math.cos(k * 0.45), cy + 90 * math.sin(k * 0.45)) for k in range(40)]  # ~3 voltas
    feed(pts, spin_done)


def spin_done():
    check("girar no ar dispara fala de giro (na fila, depois do arraste)", "girando" in cats() + said)
    w._end_drag()
    QTimer.singleShot(14000, landed)


def landed():
    check("depois do giro o pouso é tonta", "tonta" in said and "solta" not in said)
    check("ordem: arraste -> giro -> tonta", [c for c in said if c in ("arrastada", "girando", "tonta")]
          == ["arrastada", "girando", "tonta"])
    w._start_drag()  # sacudir de um lado para o outro também deixa tonta
    feed([(cx + (80 if (k // 3) % 2 else -80) + k, cy) for k in range(36)], shaken)


def shaken():
    check("sacudir de um lado para o outro também conta", w.spun)
    w._end_drag()
    qa.exit(1 if fails else 0)


QTimer.singleShot(500, straight)
QTimer.singleShot(45000, lambda: (print("timeout"), qa.exit(2)))
sys.exit(qa.exec())
