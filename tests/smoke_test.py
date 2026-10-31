"""Toca todas as animações em velocidade alta (offscreen) e verifica quadros/erros.

Uso: python tests/smoke_test.py
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from ceci.settings import Settings  # noqa: E402
from ceci.window import CeciWindow  # noqa: E402

app = QApplication(sys.argv)
s = Settings()
s["speed"] = 25.0
s["follow_mouse"] = False
win = CeciWindow(s)
win.set_start_pos()
win.show()
ids = [a for a in win.sprites.anims if a not in ("idle", "dormindo", "caminhar", "seguir_mouse")]
errors, shown = [], []
win.player.frame.connect(lambda st, new: shown.append(st) if st[0] and win.cur is None else None)


def run_next():
    if not ids:
        print("frames sem pixmap:", shown or "nenhum")
        print("erros:", errors or "nenhum")
        app.exit(1 if errors or shown else 0)
        return
    aid = ids.pop(0)
    print("tocando", aid, flush=True)
    if not win.play(aid, force=True, loops=1, on_done=lambda: QTimer.singleShot(0, run_next)):
        errors.append(f"não tocou {aid}")
        QTimer.singleShot(0, run_next)


sys.excepthook = lambda *a: (errors.append(repr(a[1])), sys.__excepthook__(*a))
QTimer.singleShot(0, run_next)
QTimer.singleShot(60000, lambda: (print("timeout em", win.player.aid), app.exit(2)))
sys.exit(app.exec())
