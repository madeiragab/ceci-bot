"""Janelas do usuário (ceci/desktop.py): nativo -> lógico com telas falsas, bordas livres com janelas falsas e,
de verdade, janelas de OUTRO processo (as da Ceci ficam de fora de propósito): a de cima corta a borda da de baixo.

Uso: python tests/desktop_test.py   (abre duas janelinhas por alguns segundos, sem roubar o foco)
"""
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from PySide6.QtCore import QPoint, QRect  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from ceci import desktop as D  # noqa: E402

qa = QApplication(sys.argv)
fails = []


def check(name, cond):
    print(("ok   " if cond else "FALHA"), name)
    if not cond:
        fails.append(name)


def win(h, x, y, w, hh, maxi=False):
    return D.Win(h, f"j{h}", "x.exe", QRect(x, y, w, hh), maxi, False)


def iv(ss, h=None):
    return [(s.y, s.x0, s.x1) for s in ss if h is None or s.hwnd == h]


# ---------- nativo -> lógico (telas falsas) ----------
S1 = (QRect(0, 0, 1366, 768), 1.0, QRect(0, 0, 1366, 768), QRect(0, 0, 1366, 720))
S2 = (QRect(1366, 0, 1280, 720), 1.5, QRect(1366, 0, 1920, 1080), QRect(1366, 0, 1280, 680))
real_screens = D._screens
D._screens = lambda: [S1, S2]
check("to_logical: tela com dpr 1.0 não muda", D.to_logical(500, 300) == QPoint(500, 300))
check("to_logical: tela 1.5 mantém o canto e divide o resto", D.to_logical(1366 + 960, 540) == QPoint(1366 + 640, 360))
check("to_native: volta para o nativo", D.to_native(1366 + 640, 360) == QPoint(1366 + 960, 540))
check("fora de toda tela: usa a mais perto", D.to_logical(4000, 90) == QPoint(1366 + round(2634 / 1.5), 60))
check("retângulo pelos cantos (tela 1.5)", D._lrect(1666, 150, 2266, 750, D._screens()) == QRect(1566, 100, 400, 400))
check("direita exclusiva na divisa das telas fica na tela da janela",
      D._lrect(366, 0, 1366, 720, D._screens()) == QRect(366, 0, 1000, 720))

# ---------- bordas livres (janelas falsas, a de cima primeiro) ----------
A = [QRect(0, 0, 1366, 720)]
check("borda livre inteira", iv(D.edges([win(1, 300, 300, 500, 300)], A)) == [(300, 300, 799)])
check("janela acima no meio parte a borda em dois",
      iv(D.edges([win(2, 450, 250, 200, 200), win(1, 300, 300, 500, 300)], A), 1) == [(300, 300, 449), (300, 650, 799)])
check("janela acima de um lado corta só aquele lado",
      iv(D.edges([win(2, 600, 250, 400, 200), win(1, 300, 300, 500, 300)], A), 1) == [(300, 300, 599)])
check("coberta inteira: nada", iv(D.edges([win(2, 200, 200, 800, 300), win(1, 300, 300, 500, 300)], A), 1) == [])
check("janela acima que termina antes da linha não cobre",
      iv(D.edges([win(2, 400, 100, 300, 199), win(1, 300, 300, 500, 300)], A), 1) == [(300, 300, 799)])
check("janela acima que começa ou termina bem na linha cobre",
      iv(D.edges([win(2, 400, 300, 100, 100), win(3, 600, 200, 100, 101), win(1, 300, 300, 500, 300)], A), 1)
      == [(300, 300, 399), (300, 500, 599), (300, 700, 799)])
check("janela de baixo não cobre a de cima",
      iv(D.edges([win(1, 300, 300, 500, 300), win(2, 450, 250, 200, 200)], A), 1) == [(300, 300, 799)])
check("maximizada não vira lugar, mas cobre as de baixo",
      D.edges([win(2, 0, 0, 1366, 720, True), win(1, 300, 300, 500, 300)], A) == [])
check("top_margin: precisa de espaço acima da borda",
      iv(D.edges([win(1, 300, 89, 500, 300), win(2, 900, 90, 300, 300)], A, top_margin=90)) == [(90, 900, 1199)])
check("borda no fim da área útil (ou abaixo) fica de fora",
      iv(D.edges([win(1, 300, 719, 500, 49), win(2, 300, 730, 500, 30), win(3, 300, 700, 500, 60)], A))
      == [(700, 300, 799)])
check("cortada na área útil (janela meio fora da tela)",
      iv(D.edges([win(1, -100, 300, 500, 300), win(2, 1200, 400, 500, 300)], A)) == [(300, 0, 399), (400, 1200, 1365)])
check("min_width: pedaço de 59 sai, de 60 fica",
      iv(D.edges([win(2, 359, 250, 381, 100), win(1, 300, 300, 500, 300)], A), 1) == [(300, 740, 799)])
check("em ordem de y", [s.y for s in D.edges([win(1, 0, 500, 300, 100), win(2, 400, 200, 300, 100),
                                              win(3, 800, 350, 300, 100)], A)] == [200, 350, 500])
check("duas telas: a borda que atravessa vira um pedaço em cada",
      iv(D.edges([win(1, 1200, 300, 400, 200)], [S1[3], S2[3]])) == [(300, 1200, 1365), (300, 1366, 1599)])
ws = [win(2, 450, 250, 200, 200), win(1, 300, 300, 500, 300)]
s_ok, s_no = D.surface_at(1, 700, ws), D.surface_at(1, 500, ws)
check("surface_at: pedaço que contém x; None se x está coberto",
      s_ok is not None and (s_ok.x0, s_ok.x1) == (650, 799) and s_no is None and D.surface_at(9, 700, ws) is None)
D._screens = real_screens

# ---------- de verdade: janelas de outro processo ----------
CHILD = r"""
import sys
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication, QWidget
x, y, w, h, title, framed, secs = sys.argv[1:8]
qa = QApplication([])
f = Qt.Window | Qt.WindowStaysOnTopHint | Qt.WindowDoesNotAcceptFocus
if framed == "0":
    f |= Qt.FramelessWindowHint
win = QWidget(None, f)
win.setWindowTitle(title)
win.setStyleSheet("background: #d9a066")
win.setGeometry(int(x), int(y), int(w), int(h))
win.show()
QTimer.singleShot(int(float(secs) * 1000), qa.quit)
print(int(win.winId()), flush=True)
qa.exec()
"""
procs = []


def spawn(x, y, w, h, title, framed, secs=15):
    p = subprocess.Popen([sys.executable, "-c", CHILD, str(x), str(y), str(w), str(h), title, framed, str(secs)],
                         stdout=subprocess.PIPE, text=True)
    procs.append(p)
    line = p.stdout.readline().strip()
    return int(line) if line.isdigit() else 0


def wait(cond, ms=5000):
    end = time.monotonic() + ms / 1000
    while not cond() and time.monotonic() < end:
        time.sleep(0.05)
    return cond()


def find(h):
    return next((w for w in D.windows() if w.hwnd == h), None)


def mean_ms(f, n=50):
    f()
    t = time.perf_counter()
    for _ in range(n):
        f()
    return (time.perf_counter() - t) / n * 1000


if sys.platform != "win32" or qa.platformName() != "windows":
    print("(pulado: janelas de verdade só no Windows, sem QT_QPA_PLATFORM=offscreen)")
else:
    tag, ha, hb = f"ceci-desktop-test-{os.getpid()}", 0, 0
    try:
        ha = spawn(300, 300, 500, 300, tag + "-A", "0")
        check("outro processo abriu a janela A", ha and wait(lambda: find(ha) is not None))
        a = find(ha)
        if a:
            print(f"     (A: {a.rect}, exe {a.exe})")
            check("A: retângulo lógico exato (300,300 500x300), exe python, não é navegador",
                  a.rect == QRect(300, 300, 500, 300) and a.exe.startswith("python") and not a.browser)
            check("A: rect_of acompanha sem EnumWindows", D.rect_of(ha) == a.rect and not D.is_maximized(ha))
            check("A: borda de cima livre de 300 a 799", (300, 300, 799) in iv(D.surfaces(top_margin=90), ha))
        hb = spawn(450, 280, 200, 200, tag + "-B", "1")
        check("outro processo abriu a janela B (com moldura, por cima da A)", hb and wait(lambda: find(hb) is not None))
        ws = D.windows()
        hs = [w.hwnd for w in ws]
        b = find(hb)
        if a and b:
            print(f"     (B: {b.rect})")
            r = D.W.RECT()
            D._u.GetWindowRect(hb, D.ctypes.byref(r))
            print(f"     (B GetWindowRect nativo: {r.left},{r.top},{r.right},{r.bottom}; moldura estendida: "
                  f"{b.rect.left()},{b.rect.top()},{b.rect.right() + 1},{b.rect.bottom() + 1})")
            check("B: moldura estendida tira a borda invisível (mais estreita que GetWindowRect, mesmo topo)",
                  r.right - r.left > b.rect.width() and r.left < b.rect.left() and r.top == b.rect.top())
            check("ordem Z: B (mais nova, por cima) vem antes da A", hb in hs and ha in hs and hs.index(hb) < hs.index(ha))
            got = iv(D.surfaces(ws, top_margin=90), ha)
            want = [(300, 300, b.rect.left() - 1), (300, b.rect.right() + 1, 799)]
            print(f"     (bordas livres da A: {got})")
            check("A: borda partida em dois pela B", b.rect.top() < 300 < b.rect.bottom() and got == want)
            sa, sn = D.surface_at(ha, 320), D.surface_at(ha, b.rect.center().x())
            check("surface_at: x livre acha o pedaço; x embaixo da B dá None",
                  sa is not None and (sa.y, sa.x0, sa.x1) == want[0] and sn is None)
            check("tempos: windows() < 50 ms, rect_of < 2 ms",
                  mean_ms(D.windows) < 50 and mean_ms(lambda: D.rect_of(ha)) < 2)
            print(f"     (média de 50: windows {mean_ms(D.windows):.3f} ms, surfaces "
                  f"{mean_ms(lambda: D.surfaces(top_margin=90)):.3f} ms, rect_of {mean_ms(lambda: D.rect_of(ha)):.4f} ms,"
                  f" surface_at {mean_ms(lambda: D.surface_at(ha, 320)):.3f} ms, foreground "
                  f"{mean_ms(D.foreground):.4f} ms)")
        procs[-1].kill()
        procs[-1].wait()
        check("B fechou: rect_of None e a borda da A volta inteira",
              wait(lambda: D.rect_of(hb) is None) and wait(lambda: (300, 300, 799) in iv(D.surfaces(), ha)))
        check("nenhuma janela deste processo aparece", all(D._pid(w.hwnd) != os.getpid() for w in D.windows()))
        fg = D.foreground()
        check("foreground nunca é deste processo", fg is None or D._pid(fg.hwnd) != os.getpid())
    finally:
        for p in procs:
            if p.poll() is None:
                p.kill()
            p.wait()
    check("janelas de teste fechadas: rect_of None", wait(lambda: not any(D.rect_of(h) for h in (ha, hb) if h)))

print("\n" + ("TUDO OK" if not fails else f"{len(fails)} FALHA(S): {fails}"))
sys.exit(1 if fails else 0)
