"""Fechar: do meio da tela ela anda até o canto mais perto, corre e os quadros finais ficam presos na
borda (direita ou esquerda, espelhado). Só depois o app fecha.

Uso: python tests/quit_test.py
"""
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


def run(side, next_step):
    app = M.App(qa)
    app.s.save = lambda: None  # não mexe nas configurações do usuário
    app.s["speed"] = 4.0
    w = app.win
    w.show()
    a = w.area()
    x = a.left() + a.width() * (0.42 if side == "left" else 0.58)
    w.foot = QPointF(x, w.ground())
    w._place()
    seen, edges = [], []

    def on_frame(st, new):
        seen.append((w.player.aid, st[0], st[1]))
        if w.player.aid == "saida" and st[0] == 21 and st[1] in (4, 6, 7) and w.cur:
            edges.append(w.foot.x() + w.cur.ox if w.player.mirror else w.foot.x() + w.cur.ox + w.cur.w)
    w.player.frame.connect(on_frame)
    closed = []
    app.qapp = type("Q", (), {"quit": lambda self: closed.append(True)})()
    app.quit_animated()

    def done():
        aids = [s[0] for s in seen]
        check(f"{side}: andou antes de sair", "caminhar" in aids and aids.index("caminhar") < aids.index("saida"))
        check(f"{side}: saiu espelhada só no canto esquerdo", w.player.mirror == (side == "left"))
        edge = a.left() if side == "left" else a.right() + 1
        check(f"{side}: quadros 4/6/7 presos na borda", edges and all(abs(e - edge) < 1.5 for e in edges))
        check(f"{side}: app fechou só no fim da animação", closed == [True])
        w.hide()
        next_step()
    QTimer.singleShot(9000, done)


run("right", lambda: run("left", lambda: qa.exit(1 if fails else 0)))
QTimer.singleShot(25000, lambda: (print("timeout"), qa.exit(2)))
sys.exit(qa.exec())
