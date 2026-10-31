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

from PySide6.QtCore import QEvent, QPointF, Qt, QTimer  # noqa: E402
from PySide6.QtGui import QMouseEvent  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import main as M  # noqa: E402
M.fullscreen_app_active = lambda: False  # tela cheia de verdade no PC (vídeo, jogo) não entra no teste
from ceci.window import CANVAS_H, INTERACT, PET_CONFIRM, PET_PASSES  # noqa: E402

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


def fire_click():  # o clique simples espera o intervalo do clique duplo; o teste não precisa esperar
    if w.click_timer.isActive():
        w.click_timer.stop()
        w._click()


def click(pos):
    sp.hide()
    w.play("idle", force=True, cut=True)
    QTest.mouseClick(w, Qt.LeftButton, Qt.NoModifier, pos.toPoint())
    fire_click()


def step1():
    check("ponto da cabeça é cabeça e o do corpo é corpo", w._hit(head) == "head" and w._hit(body) == "body")
    click(body)
    check("clique no corpo = Interagir", w.player.aid in INTERACT)
    check("clique fala uma frase de clique", sp.bubble.cat == "clique")
    click(head)
    check("clique na cabeça também = Interagir (não é carinho)", w.player.aid in INTERACT
          and w.player.aid != "carinho")
    sp.hide()
    w.play("idle", force=True, cut=True)
    dbl = []
    w.double_clicked.connect(lambda: dbl.append(1))
    QTest.mouseDClick(w, Qt.LeftButton, Qt.NoModifier, body.toPoint())
    check("clique duplo = caixinha, sem Interagir", dbl == [1] and not w.click_timer.isActive()
          and w.player.aid not in INTERACT)
    QTimer.singleShot(200, step2)


def rub(points):
    w.rub_last = None
    for p in points:
        w._rub(p)


def zigzag():
    zig = []
    for n in range(PET_PASSES + 2):  # vai e volta várias vezes sobre a cabeça
        xs = range(11) if n % 2 == 0 else range(10, -1, -1)
        zig += [head + QPointF(-30 * s + 6 * s * k, 0) for k in xs]
    return zig


def step2():
    w.play("idle", force=True, cut=True)
    w.last_pet = 0.0
    rub([head + QPointF(-30 * s + 6 * s * k, 0) for k in range(11)])  # uma passada só, sem voltar
    # mira chegando na cabeça: caminho torto, com correções nos dois eixos (antes somava e virava carinho)
    aim, p = [], head + QPointF(-140 * s, 160 * s)
    for k, (dx, dy) in enumerate([(30, -40), (25, -35), (-18, -30), (28, -25), (-20, 22), (24, -26), (-22, 20),
                                  (26, -24), (-24, 22), (20, -18), (10, 4), (-6, -5)]):
        p = p + QPointF(dx * s, dy * s)
        aim.append(QPointF(p))
    rub(aim)
    QTimer.singleShot(PET_CONFIRM + 150, step2b)


def step2b():
    check("uma passada só ou a mira chegando não viram carinho", w.player.aid != "carinho")
    rub(zigzag())
    QTimer.singleShot(PET_CONFIRM + 150, step2c)


def step2c():
    check("passar o mouse várias vezes pela cabeça = carinho", w.player.aid == "carinho")
    w.play("idle", force=True, cut=True)
    w.last_pet = 0.0
    rub(zigzag())  # mexeu bastante e clicou logo em seguida: vale o clique
    QTest.mouseClick(w, Qt.LeftButton, Qt.NoModifier, head.toPoint())
    QTimer.singleShot(PET_CONFIRM + 150, step2d)


def step2d():
    check("mexer e clicar logo depois = Interagir, não carinho", w.player.aid in INTERACT)
    QTimer.singleShot(200, step_hold)


def mev(kind, pos, buttons):
    gp = w.mapToGlobal(pos.toPoint())
    QApplication.sendEvent(w, QMouseEvent(kind, QPointF(pos), QPointF(gp), Qt.LeftButton, buttons, Qt.NoModifier))


def step_hold():
    sp.hide()
    w.play("idle", force=True, cut=True)
    mev(QEvent.MouseButtonPress, body, Qt.LeftButton)  # clique com a mão tremendo (14 px)
    mev(QEvent.MouseMove, body + QPointF(9, 5), Qt.LeftButton)
    check("clique tremido não levanta a Ceci", not w.dragging)
    mev(QEvent.MouseButtonRelease, body + QPointF(9, 5), Qt.NoButton)
    fire_click()
    check("clique tremido = Interagir", w.player.aid in INTERACT)
    w.play("idle", force=True, cut=True)
    mev(QEvent.MouseButtonPress, body, Qt.LeftButton)
    QTimer.singleShot(320, step_hold2)


def step_hold2():
    mev(QEvent.MouseMove, body + QPointF(8, 4), Qt.LeftButton)  # segurou e puxou: aí sim é arraste
    check("segurar e puxar = arrastar", w.dragging and w.player.aid == "arrastada")
    mev(QEvent.MouseButtonRelease, body + QPointF(8, 4), Qt.NoButton)
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
        name = f"CeciBot.Teste.{os.getpid()}"  # nome próprio: não esbarra na Ceci que estiver aberta
        check("primeira Ceci abre", not M.already_running(name))
        check("segunda Ceci não abre", M.already_running(name))
    qa.exit(1 if fails else 0)


QTimer.singleShot(300, step1)
QTimer.singleShot(20000, lambda: (print("timeout"), qa.exit(2)))
sys.exit(qa.exec())
