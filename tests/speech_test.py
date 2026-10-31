"""Falas no balão: escreve letra a letra em cima da cabeça, reage a clique/arraste/pouso, não repete
frase antes de esgotar a categoria, nunca corta uma fala com outra (fila), respeita o liga/desliga e
só sai correndo depois do tchau.

Uso: python tests/speech_test.py   (grava prévias do balão em _preview/balao_*.png)
"""
import os
import sys
import tempfile
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["CECI_CONFIG_DIR"] = tempfile.mkdtemp(prefix="cecibot_test_")  # nunca as do usuário
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from PySide6.QtCore import QPoint, QPointF, Qt, QTimer  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import main as M  # noqa: E402
M.fullscreen_app_active = lambda: False  # tela cheia de verdade no PC (vídeo, jogo) não entra no teste
from ceci.speech import REACT  # noqa: E402

qa = QApplication(sys.argv)
fails = []
PREV = os.path.join(ROOT, "_preview")
os.makedirs(PREV, exist_ok=True)


def check(name, cond):
    print(("ok   " if cond else "FALHA"), name)
    if not cond:
        fails.append(name)


app = M.App(qa)
app.s.save = lambda: None  # não mexe nas configurações do usuário
app.s["door_entrance"] = False
app.s["follow_mouse"] = False
w, sp, b = app.win, app.speech, app.speech.bubble
bank = sp.bank
s = w.sprites.scale
check("todas as categorias usadas existem no banco",
      all(c in bank and bank[c] for c in {r[0] for r in REACT.values()} |
          {"clique", "solta", "acordando", "saida", "raras", "esperando", "idle", "inicio"}))
app.start()
app.beh.stop()  # sem rotina automática no meio do teste


def inside(r):
    a = w.area()
    return a.left() <= r.left() and r.right() <= a.right() and a.top() <= r.top() and r.bottom() <= a.bottom()


def wait_for(cond, then, timeout=15.0):
    t0 = time.monotonic()

    def poll():
        if cond() or time.monotonic() - t0 > timeout:
            then()
        else:
            QTimer.singleShot(40, poll)
    poll()


log = []  # cada frase nova: (categoria anterior, estado anterior, nova categoria)
_start = b.start


def rec(text, cat, prio):
    log.append((b.cat, b.state, cat))
    _start(text, cat, prio)


b.start = rec


def t_typing():
    check("abre falando uma frase de início", b.active() and b.cat == "inicio" and b.text in bank["inicio"])
    check("escreve letra a letra (meio da frase)", 0 < b.n < len(b.text))
    g = b.geometry()
    check("balão em cima da cabeça, sem cobrir o rosto", b.tail == "down" and g.bottom() < w.foot.y() - 240 * s)
    check("rabicho aponta para ela", abs(g.left() + b.tail_at - w.foot.x()) < 2)
    check("balão inteiro dentro da tela", inside(g))
    text = b.text
    hit = w.anchor + QPointF(0, -110 * s)
    QTest.mouseClick(w, Qt.LeftButton, Qt.NoModifier, hit.toPoint())
    check("clique no meio da frase não corta: entra na fila", b.cat == "inicio" and b.text == text
          and [q[0] for q in sp.queue] == ["clique"])
    w._start_drag()
    check("arrastar também espera na fila", [q[0] for q in sp.queue] == ["clique", "arrastada"])
    a = w.area()
    w._drag_to(QPointF(w.foot.x(), a.top() + 335 * s))
    wait_for(lambda: b.cat == "clique", t_click)


def t_click():
    check("depois do início vem o clique", b.cat == "clique" and b.text in bank["clique"])
    wait_for(lambda: b.cat == "arrastada" and b.n > 3, t_drag)


def t_drag():
    check("depois do clique vem o arraste", b.cat == "arrastada")
    check("lá no alto o balão vai para o lado da cabeça", b.tail in ("left", "right") and inside(b.geometry()))
    b.grab().save(os.path.join(PREV, "balao_lado.png"))
    w._end_drag()
    wait_for(lambda: b.cat == "solta" and b.state == "hold", t_landed)


def t_landed():
    b.grab().save(os.path.join(PREV, "balao_cima.png"))
    check("ao cair no chão fala de pouso (depois do arraste)", b.cat == "solta" and b.text in bank["solta"])
    check("balão acompanhou a queda (de volta em cima)", b.tail == "down")
    check("nenhuma frase foi cortada no meio", log and all(st != "typing" for _, st, _ in log))
    check("ordem certa", [c for _, _, c in log][:4] == ["inicio", "clique", "arrastada", "solta"])
    picks = [sp.pick("gato") for _ in bank["gato"]]
    check("não repete frase antes de esgotar a categoria", sorted(picks) == sorted(bank["gato"]))
    sp.last_auto = time.monotonic()
    check("falas automáticas respeitam o intervalo", not sp._auto_ok(1.0))
    check("automática com balão ocupado é descartada (não entra na fila)", not sp.say("idle") and not sp.queue)
    app.s["speech"] = False
    sp.apply_settings()
    check("desligado: nenhuma fala e balão some", not sp.say("idle", 3, True) and b.isHidden())
    app.s["speech"] = True
    sp.apply_settings()
    sp.say("dormindo", 3, True)
    wait_for(lambda: b.state == "off", t_gone, timeout=20)  # pode ter frase na fila antes


def t_gone():
    check("depois de ler, o balão some sozinho", b.state == "off" and b.isHidden())
    app.s["speed"] = 4.0
    a = w.area()
    w.foot = QPointF(a.left() + a.width() * 0.6, w.ground())
    w._place()
    seen = {"full": False, "run": None}

    def poll():
        if b.cat == "saida" and b.state == "hold":
            seen["full"] = True
    pt = QTimer(timeout=poll)
    pt.start(30)

    def on_frame(st, new):
        if new and w.player.aid == "saida" and seen["run"] is None:
            seen["run"] = (seen["full"], b.isHidden())
    w.player.frame.connect(on_frame)
    closed = []
    app.qapp = type("Q", (), {"quit": lambda self: closed.append(True)})()
    app.quit_animated()
    check("ao fechar fala um tchau", b.cat == "saida" and b.text in bank["saida"])

    def done():
        pt.stop()
        check("só sai correndo depois de terminar o tchau", seen["run"] and seen["run"][0])
        check("o balão some quando ela corre", seen["run"] and seen["run"][1])
        check("app fechou no fim", closed == [True])
        qa.exit(1 if fails else 0)
    QTimer.singleShot(12000, done)


QTimer.singleShot(1000, t_typing)
QTimer.singleShot(70000, lambda: (print("timeout"), qa.exit(2)))
sys.exit(qa.exec())
