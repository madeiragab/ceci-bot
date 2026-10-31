"""Regras do motor: miolo repete; trocar no miolo toca o final antes; corte (arraste) é imediato.

Uso: python tests/engine_test.py
"""
import os
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["CECI_CONFIG_DIR"] = tempfile.mkdtemp(prefix="cecibot_test_")  # nunca as do usuário
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import QCoreApplication, QTimer  # noqa: E402

from ceci.engine import Player  # noqa: E402

app = QCoreApplication(sys.argv)
ANIMS = {
    "idle": dict(seq=[[1, 0, 1000]], loop=[0, 0], loops="inf", prio=0, next="idle"),
    "ler": dict(seq=[[2, 0, 20], [2, 1, 20], [2, 2, 20], [2, 3, 20], [2, 4, 20]], loop=[1, 2], loops="inf",
                prio=1, next="idle"),  # 0 pega livro, 1-2 folheia, 3-4 guarda
    "carinho": dict(seq=[[3, 0, 20], [3, 1, 20]], loop=None, prio=3, next="idle"),
    "arrasto": dict(seq=[[4, 0, 20]], loop=None, prio=4, next="idle"),
}
p = Player(ANIMS, {"speed": 1.0})
log = []
p.frame.connect(lambda st, new: log.append((st[0], st[1])))
fails = []


def check(name, cond):
    print(("ok   " if cond else "FALHA"), name)
    if not cond:
        fails.append(name)


def step1():
    p.play("ler", force=True)
    QTimer.singleShot(300, step2)  # deixa o miolo repetir algumas vezes


def step2():
    folheios = sum(1 for f in log if f in ((2, 1), (2, 2)))
    check("miolo repete enquanto ninguém pede troca", folheios >= 6)
    check("final ainda não tocou", (2, 3) not in log)
    log.clear()
    p.play("carinho", force=True)  # pedido no meio do miolo
    QTimer.singleShot(400, step3)


def step3():
    seq = [f for f in log if f[0] in (2, 3)]
    check("final (guardar livro) toca antes do carinho", seq[:2] == [(2, 3), (2, 4)] and (3, 0) in seq)
    log.clear()
    p.play("ler", force=True)
    QTimer.singleShot(100, step4)


def step4():
    log.clear()
    p.play("arrasto", force=True, cut=True)
    check("arraste corta na hora (sem final)", log[:1] == [(4, 0)])
    app.exit(1 if fails else 0)


QTimer.singleShot(0, step1)
QTimer.singleShot(5000, lambda: (print("timeout"), app.exit(2)))
sys.exit(app.exec())
