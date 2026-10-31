"""Animações presas à parede: ela anda até a borda antes (sem teleporte) e o quadro preso continua de onde
o último quadro solto parou. Na saída, a perna aparece uma vez só (corrida → meio fora → livro → mão).

Uso: python tests/edge_test.py   (grava _preview/esconder_strip.png e _preview/saida_strip.png)
"""
import os
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["CECI_CONFIG_DIR"] = tempfile.mkdtemp(prefix="cecibot_test_")  # nunca as do usuário
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from PySide6.QtCore import QPointF, QRect, QTimer, Qt  # noqa: E402
from PySide6.QtGui import QColor, QImage, QPainter  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import main as M  # noqa: E402

qa = QApplication(sys.argv)
fails = []


def check(name, cond):
    print(("ok   " if cond else "FALHA"), name)
    if not cond:
        fails.append(name)


app = M.App(qa)
app.s["speed"] = 2.0
app.s["speech"] = False
app.s["follow_mouse"] = False
w = app.win
w.show()
w.play("idle", force=True)
s = w.sprites.scale


def strip(shots, path):
    """Quadros lado a lado, com o que passa da borda da tela pintado de cinza (o que a tela esconde)."""
    if not shots:
        return
    W = sum(i.width() + 8 for i in shots)
    H = max(i.height() for i in shots)
    out = QImage(W, H, QImage.Format_ARGB32)
    out.fill(QColor(40, 44, 52))
    p = QPainter(out)
    x = 0
    for im in shots:
        p.drawImage(x, 0, im)
        x += im.width() + 8
    p.end()
    out.save(path)


def shot():
    im = w.grab().toImage().convertToFormat(QImage.Format_ARGB32)
    edge = w.area().right() + 1 - w.x()  # borda da tela em coordenadas da janela
    if edge < im.width():
        p = QPainter(im)
        p.fillRect(QRect(int(edge), 0, im.width() - int(edge), im.height()), QColor(90, 90, 90, 230))
        p.end()
    return im


def run_hide(start_x, label, next_step):
    a = w.area()
    w.foot = QPointF(start_x, w.ground())
    w._place()
    seen, rec, shots = [], {}, []
    edge = a.right() + 1

    def on_frame(st, new):
        seen.append((w.player.aid, st[1]))
        if w.player.aid == "escondendo" and w.cur:
            i = w.player.i
            rec.setdefault(i, (w.foot.x() + w.cur.ox, w.foot.x() + w.cur.ox + w.cur.w))
            if i in (4, 5, 6, 7):
                shots.append(shot())
    w.player.frame.connect(on_frame)
    w.play("escondendo", force=True)

    def done():
        w.player.frame.disconnect(on_frame)
        aids = [x[0] for x in seen]
        check(f"{label}: anda até a borda antes de esconder", "caminhar" in aids and "escondendo" in aids
              and aids.index("caminhar") < aids.index("escondendo"))
        check(f"{label}: agachada encosta na borda (quadro 5)", 5 in rec and abs(rec[5][1] - edge) <= 4)
        check(f"{label}: quadro preso na borda (6)", 6 in rec and abs(rec[6][1] - edge) <= 2)
        check(f"{label}: sem pulo para trás ao prender", 5 in rec and 6 in rec and rec[6][0] >= rec[5][0] - 2
              and rec[6][0] - rec[5][0] < 40 * s)
        if 5 in rec:
            print(f"     ({label}: borda {edge:.0f}, agachada termina em {rec[5][1]:.1f}, presa em {rec.get(6, (0, 0))[1]:.1f})")
        strip(shots, os.path.join(ROOT, "_preview", f"esconder_strip_{label}.png"))
        w.stop_walk()
        w.play("idle", force=True, cut=True)
        QTimer.singleShot(200, next_step)
    QTimer.singleShot(16000, done)


def run_exit():
    a = w.area()
    w.foot = QPointF(a.left() + a.width() * 0.6, w.ground())
    w._place()
    order, shots = [], []

    def on_frame(st, new):
        if w.player.aid == "saida" and st[0] == 21:
            order.append(st[1])
            shots.append(shot())
            QTimer.singleShot(int(min(420, st[2] / 2 * 0.5) / 2), lambda: shots.append(shot()))  # meio do dissolve
    w.player.frame.connect(on_frame)
    closed = []
    app.qapp = type("Q", (), {"quit": lambda self: closed.append(True)})()
    app.quit_animated()

    def done():
        check("saída: corrida → meio fora → livro → mão (perna uma vez só)", order == [0, 1, 2, 4, 3, 5, 6, 7])
        check("saída: app fechou no fim", closed == [True])
        strip(shots, os.path.join(ROOT, "_preview", "saida_strip.png"))
        qa.exit(1 if fails else 0)
    QTimer.singleShot(9000, done)


a0 = w.area()
QTimer.singleShot(300, lambda: run_hide(a0.left() + a0.width() * 0.4, "meio",
                                        lambda: run_hide(a0.right() - 20 * s, "colada", run_exit)))
QTimer.singleShot(60000, lambda: (print("timeout"), qa.exit(2)))
sys.exit(qa.exec())
