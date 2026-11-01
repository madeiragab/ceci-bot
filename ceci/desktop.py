"""Janelas do usuário, só olhando (Win32 via ctypes): qual está na frente, onde cada uma está e que pedaço da
borda de cima está livre para a Ceci sentar. Nunca clica, digita, move, foca nem muda janela nenhuma.

O Win32 dá pixels nativos; o Qt 6 (DPI por monitor) usa lógicos: tudo aqui sai em coordenadas lógicas do Qt.
Precisa do QGuiApplication já criado (é ele que liga o DPI por monitor e conhece as telas)."""
import ctypes
import os
import sys
from dataclasses import dataclass

from PySide6.QtCore import QPoint, QRect
from PySide6.QtGui import QGuiApplication

ON = sys.platform == "win32"
BROWSERS = frozenset((
    "chrome.exe", "msedge.exe", "firefox.exe", "brave.exe", "opera.exe", "opera_gx.exe", "vivaldi.exe", "arc.exe",
    "zen.exe", "librewolf.exe", "waterfox.exe", "chromium.exe", "yandex.exe", "floorp.exe", "thorium.exe",
    "palemoon.exe", "iexplore.exe", "whale.exe", "duckduckgo.exe", "comet.exe", "maxthon.exe", "seamonkey.exe"))
# área de trabalho, barra de tarefas e superfícies do próprio Windows (Iniciar, Pesquisa, Alt+Tab, bandeja)
SHELL = frozenset(("Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd", "Windows.UI.Core.CoreWindow",
                   "XamlExplorerHostIslandWindow", "ForegroundStaging", "MultitaskingViewFrame",
                   "TopLevelWindowForOverflowXamlIsland", "NotifyIconOverflowWindow"))
GWL_EXSTYLE, WS_EX_TOOLWINDOW = -20, 0x80
DWMWA_EXTENDED_FRAME_BOUNDS, DWMWA_CLOAKED = 9, 14
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_PID = os.getpid()


@dataclass
class Win:
    hwnd: int
    title: str
    exe: str  # nome do executável em minúsculas ('' se não deu para saber)
    rect: QRect  # lógico, sem a borda invisível de redimensionar nem a sombra
    maximized: bool
    browser: bool


@dataclass
class Surface:
    """Pedaço livre da borda de cima de uma janela: linha y, de x0 até x1 (inclusivos, como QRect.left/right)."""
    hwnd: int
    y: int
    x0: int
    x1: int
    title: str
    el: str = ""  # item da página (botão, imagem...; ceci/page.py) em vez da borda da janela


# ---------- nativo <-> lógico (sem Win32: dá para testar com telas falsas) ----------

def _screens():
    """[(geometria lógica, dpr, retângulo nativo, área útil)] de cada tela."""
    out = []
    for s in QGuiApplication.screens():
        g, d = s.geometry(), s.devicePixelRatio()
        out.append((g, d, QRect(g.x(), g.y(), round(g.width() * d), round(g.height() * d)), s.availableGeometry()))
    return out


def _pick(scr, x, y, k):
    """Tela cujo retângulo k (0 lógico, 2 nativo) tem o ponto; senão a mais perto; None sem telas."""
    best, dist = None, None
    for s in scr:
        r = s[k]
        d = max(r.left() - x, 0, x - r.right()) + max(r.top() - y, 0, y - r.bottom())
        if d == 0:
            return s
        if dist is None or d < dist:
            best, dist = s, d
    return best


def _conv(s, x, y, inv=False):
    if s is None:
        return round(x), round(y)
    o, f = s[0].topLeft(), (s[1] if inv else 1 / s[1])
    return round(o.x() + (x - o.x()) * f), round(o.y() + (y - o.y()) * f)


def to_logical(x, y, scr=None):
    """Ponto nativo (Win32) -> lógico (Qt): cada tela mantém o canto de cima à esquerda e divide o resto pelo dpr."""
    scr = _screens() if scr is None else scr
    return QPoint(*_conv(_pick(scr, x, y, 2), x, y))


def to_native(x, y, scr=None):
    """Ponto lógico (Qt) -> nativo (Win32), o inverso de to_logical."""
    scr = _screens() if scr is None else scr
    return QPoint(*_conv(_pick(scr, x, y, 0), x, y, True))


def _lrect(l, t, r, b, scr):
    """RECT nativo (direita/baixo exclusivos) -> QRect lógico; cada canto pela tela em que cai."""
    x0, y0 = _conv(_pick(scr, l, t, 2), l, t)
    x1, y1 = _conv(_pick(scr, r - 1, b - 1, 2), r, b)
    return QRect(x0, y0, x1 - x0, y1 - y0)


# ---------- bordas livres (lógica pura: lista de Win em ordem Z + áreas úteis) ----------

def _cut(ivs, a, b):
    out = []
    for x0, x1 in ivs:
        if b < x0 or a > x1:
            out.append((x0, x1))
            continue
        if x0 < a:
            out.append((x0, a - 1))
        if b < x1:
            out.append((b + 1, x1))
    return out


def edges(wins, areas, min_width=60, top_margin=0, only=None):
    """Pedaços da borda de cima de cada janela não maximizada que nenhuma janela acima (antes na lista) cobre,
    cortados na área útil de cada tela (areas: QRects) e só se sobra top_margin acima dela. only: só essa hwnd."""
    out = []
    for i, w in enumerate(wins):
        if w.maximized or (only is not None and w.hwnd != only):
            continue
        r, y = w.rect, w.rect.top()
        for a in areas:
            if not (a.top() + top_margin <= y < a.bottom()) or r.left() > a.right() or r.right() < a.left():
                continue
            ivs = [(max(r.left(), a.left()), min(r.right(), a.right()))]
            for up in wins[:i]:
                u = up.rect
                if u.top() <= y <= u.bottom():
                    ivs = _cut(ivs, u.left(), u.right())
                    if not ivs:
                        break
            out += [Surface(w.hwnd, y, x0, x1, w.title) for x0, x1 in ivs if x1 - x0 + 1 >= min_width]
    out.sort(key=lambda s: (s.y, s.x0))
    return out


# ---------- Win32 (só leitura) ----------

if ON:
    from ctypes import wintypes as W

    # instâncias próprias: os argtypes daqui não mexem no ctypes.windll que o resto do app usa
    _u, _d, _k = ctypes.WinDLL("user32"), ctypes.WinDLL("dwmapi"), ctypes.WinDLL("kernel32")
    _ENUM = ctypes.WINFUNCTYPE(W.BOOL, W.HWND, W.LPARAM)
    _GWL = "GetWindowLongPtrW" if hasattr(_u, "GetWindowLongPtrW") else "GetWindowLongW"
    _H, _B, _D, _I, _S, _P = W.HWND, W.BOOL, W.DWORD, ctypes.c_int, W.LPWSTR, ctypes.POINTER
    for _lib, _name, _res, _args in (
            (_u, "GetForegroundWindow", _H, ()), (_u, "EnumWindows", _B, (_ENUM, W.LPARAM)),
            (_u, "IsWindow", _B, (_H,)), (_u, "IsWindowVisible", _B, (_H,)), (_u, "IsIconic", _B, (_H,)),
            (_u, "IsZoomed", _B, (_H,)), (_u, "GetWindowTextLengthW", _I, (_H,)),
            (_u, "GetWindowTextW", _I, (_H, _S, _I)), (_u, "GetClassNameW", _I, (_H, _S, _I)),
            (_u, "GetWindowThreadProcessId", _D, (_H, _P(_D))), (_u, "GetWindowRect", _B, (_H, _P(W.RECT))),
            (_u, "FindWindowExW", _H, (_H, _H, W.LPCWSTR, W.LPCWSTR)), (_u, _GWL, ctypes.c_ssize_t, (_H, _I)),
            (_d, "DwmGetWindowAttribute", ctypes.c_long, (_H, _D, ctypes.c_void_p, _D)),
            (_k, "OpenProcess", W.HANDLE, (_D, _B, _D)), (_k, "CloseHandle", _B, (W.HANDLE,)),
            (_k, "QueryFullProcessImageNameW", _B, (W.HANDLE, _D, _S, _P(_D)))):
        _f = getattr(_lib, _name)
        _f.restype, _f.argtypes = _res, _args
    _exstyle = getattr(_u, _GWL)
    _found = []

    @_ENUM
    def _collect(hwnd, lp):  # fica viva no módulo; só junta as hwnds (filtro fora do callback)
        _found.append(hwnd)
        return True

_exes = {}


def _text(f, hwnd, n):
    buf = ctypes.create_unicode_buffer(n)
    f(hwnd, buf, n)
    return buf.value


def _title(hwnd):
    n = _u.GetWindowTextLengthW(hwnd)
    return _text(_u.GetWindowTextW, hwnd, n + 1) if n > 0 else ""


def _pid(hwnd):
    p = W.DWORD(0)
    _u.GetWindowThreadProcessId(hwnd, ctypes.byref(p))
    return p.value


def _cloaked(hwnd):
    """Escondida pelo DWM: em outra área de trabalho virtual, app UWP suspenso, painel do Windows fechado."""
    v = W.DWORD(0)
    return _d.DwmGetWindowAttribute(hwnd, DWMWA_CLOAKED, ctypes.byref(v), 4) == 0 and v.value != 0


def _native(hwnd):
    """(l, t, r, b) nativos sem borda invisível nem sombra (cai para GetWindowRect); None se a janela sumiu."""
    r = W.RECT()
    if _d.DwmGetWindowAttribute(hwnd, DWMWA_EXTENDED_FRAME_BOUNDS, ctypes.byref(r), ctypes.sizeof(r)) != 0 \
            and not _u.GetWindowRect(hwnd, ctypes.byref(r)):
        return None
    return r.left, r.top, r.right, r.bottom


def _exe_of(pid):
    e = _exes.get(pid)
    if e is None:
        if len(_exes) > 256:
            _exes.clear()
        e, h = "", _k.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if h:
            buf, n = ctypes.create_unicode_buffer(1024), W.DWORD(1024)
            if _k.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(n)):
                e = os.path.basename(buf.value).lower()
            _k.CloseHandle(h)
        _exes[pid] = e
    return e


def _exe(hwnd, pid):
    e = _exe_of(pid)
    if e == "applicationframehost.exe":  # app UWP: a moldura é de outro processo; o app é a janela-filha
        c = _u.FindWindowExW(hwnd, None, "Windows.UI.Core.CoreWindow", None)
        if c:
            e = _exe_of(_pid(c)) or e
    return e


def _win(hwnd, title, pid, scr, min_w=0, min_h=0):
    n = _native(hwnd)
    if n is None:
        return None
    rect = _lrect(*n, scr)
    if rect.width() < min_w or rect.height() < min_h:
        return None
    e = _exe(hwnd, pid)
    return Win(hwnd, title, e, rect, bool(_u.IsZoomed(hwnd)), e in BROWSERS)


def foreground():
    """Janela em primeiro plano; None se não há, se é da própria Ceci, da área de trabalho/barra de tarefas ou sem título."""
    if not ON:
        return None
    h = _u.GetForegroundWindow()
    if not h or _text(_u.GetClassNameW, h, 256) in SHELL:
        return None
    pid = _pid(h)
    if not pid or pid == _PID:  # antes do título: GetWindowText numa janela nossa manda mensagem
        return None
    t = _title(h)
    return _win(h, t, pid, _screens()) if t else None


def windows():
    """Janelas de programa visíveis em ordem Z, a de cima primeiro. Fora: minimizadas, cloaked, de ferramenta,
    as da Ceci, sem título, área de trabalho/barra de tarefas e as menores que 120x80 (lógicos)."""
    if not ON:
        return []
    _found.clear()
    _u.EnumWindows(_collect, 0)
    hs, scr, out = list(_found), _screens(), []
    _found.clear()
    for h in hs:
        if not h or not _u.IsWindowVisible(h) or _u.IsIconic(h) or _exstyle(h, GWL_EXSTYLE) & WS_EX_TOOLWINDOW:
            continue
        pid = _pid(h)
        if not pid or pid == _PID:
            continue
        t = _title(h)
        if not t or _text(_u.GetClassNameW, h, 256) in SHELL or _cloaked(h):
            continue
        w = _win(h, t, pid, scr, 120, 80)
        if w:
            out.append(w)
    return out


def rect_of(hwnd):
    """Retângulo lógico atual de uma janela (barato, sem EnumWindows: dá para chamar a cada 50 ms);
    None se ela sumiu, está invisível, minimizada ou cloaked."""
    if not ON or not hwnd or not _u.IsWindow(hwnd) or not _u.IsWindowVisible(hwnd) or _u.IsIconic(hwnd) \
            or _cloaked(hwnd):
        return None
    n = _native(hwnd)
    return _lrect(*n, _screens()) if n else None


def is_maximized(hwnd):
    return bool(ON and hwnd and _u.IsZoomed(hwnd))


def surfaces(wins=None, min_width=60, top_margin=0):
    """Onde a Ceci pode sentar: pedaços livres das bordas de cima das janelas (de cima da tela para baixo)."""
    if not ON:
        return []
    return edges(windows() if wins is None else wins, [s[3] for s in _screens()], min_width, top_margin)


def surface_at(hwnd, x, wins=None):
    """Pedaço livre da borda de cima dessa janela que contém x (para conferir que ninguém cobriu); senão None."""
    if not ON:
        return None
    wins = windows() if wins is None else wins
    for s in edges(wins, [s[3] for s in _screens()], 1, 0, only=hwnd):
        if s.x0 <= x <= s.x1:
            return s
    return None
