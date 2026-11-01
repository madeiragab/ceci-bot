"""Em cima das janelas, de verdade: janelas de outro processo (sempre no topo, sem pegar foco) e a Ceci real.
Solta no ar → pousa na borda de cima da janela; a janela anda → ela vai junto; a janela fecha → ela cai no
chão; pulo até outra janela; outra janela cobre a borda → ela cai; parede da tela não vale lá em cima.
Precisa da tela de verdade (não roda com QT_QPA_PLATFORM=offscreen). Uso: python tests/perch_test.py
"""
import os
import subprocess
import sys
import tempfile
import time

os.environ["CECI_CONFIG_DIR"] = tempfile.mkdtemp(prefix="cecibot_perch_")  # nunca as do usuário
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import QCoreApplication, QEventLoop, QPointF  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from ceci import desktop  # noqa: E402
from ceci.behavior import Behavior  # noqa: E402
from ceci.settings import Settings  # noqa: E402
from ceci.window import CeciWindow  # noqa: E402

if os.environ.get("QT_QPA_PLATFORM") == "offscreen" or not desktop.ON:
    print("pulado: precisa do Windows com a tela de verdade")
    sys.exit(0)

app = QApplication(sys.argv)
fails = []
CMD = os.path.join(os.environ["CECI_CONFIG_DIR"], "cmd")
# janela de outro processo que obedece um arquivo de comandos: "move x y" e "quit"
CHILD = r"""
import os, sys
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication, QWidget
x, y, w, h, title, cmd = sys.argv[1:7]
qa = QApplication([])
win = QWidget(None, Qt.Window | Qt.WindowStaysOnTopHint | Qt.WindowDoesNotAcceptFocus | Qt.FramelessWindowHint)
win.setWindowTitle(title)
win.setStyleSheet("background: #d9a066")
win.setGeometry(int(x), int(y), int(w), int(h))
win.show()
def poll():
    try:
        with open(cmd + title, encoding="utf8") as f:
            line = f.read().strip()
        os.remove(cmd + title)
    except OSError:
        return
    if line == "quit":
        qa.quit()
    elif line.startswith("move"):
        _, nx, ny = line.split()
        win.move(int(nx), int(ny))
t = QTimer()
t.timeout.connect(poll)
t.start(50)
QTimer.singleShot(60000, qa.quit)
print(int(win.winId()), flush=True)
qa.exec()
"""
procs = []


def check(name, cond):
    print(("ok   " if cond else "FALHA"), name)
    if not cond:
        fails.append(name)


def spawn(x, y, w, h, title):
    p = subprocess.Popen([sys.executable, "-c", CHILD, str(x), str(y), str(w), str(h), title, CMD],
                         stdout=subprocess.PIPE, text=True)
    procs.append(p)
    hwnd = int(p.stdout.readline().strip() or 0)
    wait(lambda: desktop.rect_of(hwnd) is not None, 3000)
    return hwnd


def send(title, line):
    with open(CMD + title, "w", encoding="utf8") as f:
        f.write(line)


def wait(cond, ms=5000):
    end = time.monotonic() + ms / 1000
    while not cond() and time.monotonic() < end:
        QCoreApplication.processEvents(QEventLoop.AllEvents, 30)
        time.sleep(0.01)
    return cond()


def pump(ms):
    wait(lambda: False, ms)


s = Settings()
s.save = lambda: None
s["follow_mouse"] = False
s["size"] = 0.25
win = CeciWindow(s)
win.set_start_pos()
win.show()
heard = []
win.interaction.connect(heard.append)
a = win.sprites.anims["arrastada"]
ground = win.area().bottom() + 1
try:
    A = spawn(300, 350, 500, 250, "CeciPerchA")
    # 1. solta no ar em cima da janela → cai e pousa na borda de cima dela
    win._start_drag()
    win._drag_to(QPointF(500, 250))
    win._end_drag()
    check("solta no ar acima da janela → caindo", win.fall_v is not None and win.player.i == a["fall"])
    wait(lambda: win.fall_v is None, 3000)
    check("pousou na borda de cima da janela (não no chão)",
          win.perch is not None and win.perch.hwnd == A and abs(win.foot.y() - 350) < 1)
    check("andar lá em cima fica dentro da borda", 300 <= win.clamp_x(0) and win.clamp_x(5000) <= 800)
    check("parede da tela não vale em cima da janela (esconder recusado)", win.play("escondendo") is False)
    # 2. a janela anda → ela vai junto
    pump(800)
    x0 = win.foot.x()
    send("CeciPerchA", "move 420 310")
    wait(lambda: abs(win.foot.y() - 310) < 1, 2000)
    check("janela arrastada: ela vai junto (x +120, y -40)",
          abs(win.foot.y() - 310) < 1 and abs(win.foot.x() - (x0 + 120)) < 2 and win.perch.hwnd == A)
    # 3. a janela fecha → ela cai até o chão
    heard.clear()
    send("CeciPerchA", "quit")
    wait(lambda: win.perch is None and win.fall_v is None and abs(win.foot.y() - ground) < 1, 4000)
    check("janela fechou: ela cai e pousa no chão", win.perch is None and abs(win.foot.y() - ground) < 1)
    check("janela fechou: fala que caiu (não 'solta' do arraste)", "caiu" in heard and "solta" not in heard)
    # 4. pulo até outra janela
    pump(1200)
    B = spawn(600, 430, 420, 200, "CeciPerchB")
    sf = desktop.surface_at(B, 800)
    check("borda livre da janela nova encontrada", sf is not None and sf.y == 430)
    heard.clear()
    check("pulo começa", win.jump_to(sf, 800))
    check("no ar: subindo, pose de queda", win.fall_v is not None and win.fall_v < 0 and win.player.aid == "arrastada")
    wait(lambda: win.fall_v is None, 4000)
    check("pulo: pousou na borda da janela, no x mirado",
          win.perch is not None and win.perch.hwnd == B and abs(win.foot.y() - 430) < 1
          and abs(win.foot.x() - 800) < 6)
    check("pulo: pouso suave (último quadro), sem 'solta'", "solta" not in heard and "janela" in heard)
    # 5. outra janela cobre a borda embaixo dela → cai
    pump(800)
    spawn(int(win.foot.x()) - 60, 380, 200, 200, "CeciPerchC")
    wait(lambda: win.perch is None and win.fall_v is None, 4000)
    check("borda coberta por outra janela: ela cai até o chão", win.perch is None and abs(win.foot.y() - ground) < 1)
    # 6. rotina: no chão ela tenta subir; em cima, sentar na borda pesa mais e esconder some
    pump(1200)
    send("CeciPerchC", "quit")
    pump(600)
    import random
    b = Behavior(win, s)
    seen = []
    orig = random.choices
    random.choices = lambda keys, weights: seen.append(dict(zip(keys, weights))) or [keys[0]]
    b.last_special = 0
    Behavior._choose(b)
    win.perch = desktop.surface_at(B, 800)
    win.perch_t = time.monotonic() - 300
    b.recent = []
    Behavior._choose(b)
    random.choices = orig
    check("rotina no chão: subir numa janela está entre as opções", "_subir" in seen[0])
    check("rotina em cima: descer aparece, esconder e subir não, sentar na borda pesa 4x",
          "_descer" in seen[1] and "escondendo" not in seen[1] and "_subir" not in seen[1]
          and seen[1].get("borda") == 4 * win.sprites.anims["borda"]["auto"])
    win.perch = None
    check("subir sozinha: acha a borda e vai até ela", win.climb() and (win.walk_target is not None
                                                                      or win.fall_v is not None))
    wait(lambda: win.perch is not None, 8000)
    check("subir sozinha: pousou numa borda de janela", win.perch is not None)
    check("descer: pula para o chão", win.jump_to(None, win.foot.x()))
    wait(lambda: win.fall_v is None, 4000)
    check("descer: no chão de novo", win.perch is None and abs(win.foot.y() - ground) < 1)
finally:
    for p in procs:
        p.kill()

print("\n" + ("TUDO OK" if not fails else f"{len(fails)} FALHA(S): {fails}"))
sys.exit(1 if fails else 0)
