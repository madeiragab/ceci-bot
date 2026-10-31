"""Ceci Bot — Fase 1: mascote interativa para a área de trabalho."""
import ctypes
import os
import random
import sys

from PySide6.QtCore import QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from ceci.behavior import Behavior
from ceci.settings import ROOT, Settings
from ceci.speech import Speech
from ceci.tray import Tray, build_menu
from ceci.ui import AnimPanel, SettingsDialog
from ceci.window import CeciWindow

ICON = os.path.join(ROOT, "assets", "icon", "ceci.png")


def fullscreen_app_active():
    """Janela em primeiro plano cobre o monitor inteiro (jogo/vídeo)? Só usa APIs do Windows."""
    if sys.platform != "win32":
        return False
    u = ctypes.windll.user32
    hwnd = u.GetForegroundWindow()
    if not hwnd:
        return False
    cls = ctypes.create_unicode_buffer(64)
    u.GetClassNameW(hwnd, cls, 64)
    if cls.value in ("Progman", "WorkerW", "Shell_TrayWnd"):
        return False

    class RECT(ctypes.Structure):
        _fields_ = [("l", ctypes.c_long), ("t", ctypes.c_long), ("r", ctypes.c_long), ("b", ctypes.c_long)]

    class MI(ctypes.Structure):
        _fields_ = [("cb", ctypes.c_ulong), ("mon", RECT), ("work", RECT), ("flags", ctypes.c_ulong)]
    r = RECT()
    u.GetWindowRect(hwnd, ctypes.byref(r))
    mi = MI(cb=ctypes.sizeof(MI))
    u.GetMonitorInfoW(u.MonitorFromWindow(hwnd, 2), ctypes.byref(mi))
    m = mi.mon
    return r.l <= m.l and r.t <= m.t and r.r >= m.r and r.b >= m.b


class App:
    def __init__(self, qapp):
        self.qapp = qapp
        self.s = Settings()
        self.win = CeciWindow(self.s)
        self.beh = Behavior(self.win, self.s)
        self.speech = Speech(self.win, self.s)
        self.win.context_menu.connect(self._menu)
        self.tray = Tray(self, ICON)
        self.panel = self.dlg = None
        self.fs_paused = False
        self.fs_timer = QTimer(timeout=self._check_fullscreen)
        self._update_fs_timer()

    def start(self):
        self.win.set_start_pos()
        self.win.show()
        if self.s["door_entrance"]:
            self.win.play("entrada", force=True, talk=True)  # não aparece parada antes da entrada
        else:
            self.win.play("idle", force=True)  # abre direto no idle novo (folha idle.png)
            self.beh.schedule()
            QTimer.singleShot(700, lambda: self.speech.say("inicio", 3, force=True))
        self.speech.restart_chat()
        self.win.update_eye_timer()
        self.win.update_breath()

    # --- menu ---
    def _menu(self, pos):
        self.beh.user_activity()
        self._ctx = build_menu(self)
        self._ctx.popup(pos)

    def interact(self):
        self.beh.user_activity()
        self.win.interact(talk=True)

    def chat(self):
        self.beh.user_activity()
        self.speech.say(random.choice(["idle", "curiosa", "conversando", "raras"]), 3, force=True)

    def stroll(self):
        """Caminha até um ponto aleatório da tela (sentido oposto se estiver perto da borda)."""
        self.beh.user_activity()
        w = self.win
        a = w.area()
        d = random.uniform(180, 420) * w.sprites.scale / 0.55
        x = w.foot.x() + (d if w.foot.x() < a.center().x() else -d)
        w.walk_to(x)

    def open_panel(self):
        if not self.panel:
            self.panel = AnimPanel(self.win, self.beh)
        self.panel.show()
        self.panel.raise_()

    def open_settings(self):
        self.dlg = SettingsDialog(self.s, self._apply)
        self.dlg.show()

    def _apply(self):
        self.win.apply_settings()
        self.speech.apply_settings()
        self._update_fs_timer()

    def set_size(self, v):
        self.s["size"] = v
        self.s.save()
        self.win.set_size(v)

    # --- visibilidade / pausa ---
    def set_paused(self, on):
        self.win.player.set_paused(on)
        self.win.update_eye_timer()
        self.win.update_breath()
        self.beh.stop() if on else self.beh.schedule()
        self.speech.hide() if on else self.speech.restart_chat()

    def hide_ceci(self):
        self.beh.stop()
        self.speech.hide()
        self.win.suspend(True)
        self.win.hide()
        self.win.update_eye_timer()

    def show_ceci(self):
        self.win.show()
        self.win.suspend(False)
        self.win.update_eye_timer()
        self.win.play("acenando", force=True)
        QTimer.singleShot(400, lambda: self.speech.say("inicio", 3, force=True))

    def _update_fs_timer(self):
        self.fs_timer.start(3000) if self.s["pause_fullscreen"] else self.fs_timer.stop()

    def _check_fullscreen(self):
        fs = fullscreen_app_active()
        if fs and not self.fs_paused and self.win.isVisible():
            self.fs_paused = True
            self.hide_ceci()
        elif not fs and self.fs_paused:
            self.fs_paused = False
            self.show_ceci()

    # --- saída ---
    def quit_animated(self):
        w = self.win
        if not w.isVisible() or w.exiting:
            self.qapp.quit()
            return
        self.beh.stop()
        self.fs_timer.stop()
        w.player.set_paused(False)
        w.eyes_off()
        w.save_pos()
        QTimer.singleShot(20000, self.qapp.quit)  # segurança
        a, s = w.area(), w.sprites.scale
        left = w.foot.x() - a.left() < a.right() - w.foot.x()  # canto mais perto
        # ponto de largada: a corrida (quadros 0-2) termina com ela saindo pela borda
        target = a.left() + 250 * s if left else a.right() + 1 - 250 * s

        self.speech.say("saida", 5, force=True)

        def go():
            w.exiting = True
            self.speech.hide()  # o balão some quando ela sai correndo
            w.play("saida", force=True, mirror=left, on_done=self.qapp.quit)

        def ready():  # só corre depois de terminar de falar o tchau
            QTimer.singleShot(self.speech.remaining_ms(), go)
        if abs(w.foot.x() - target) > 20:
            w.walk_to(target, on_done=ready, fast=True)  # sempre andando até o canto
        else:
            ready()


def already_running(name="CeciBot.SingleInstance"):
    """Outra Ceci já aberta? Duas por cima uma da outra parecem animação bugada (mutex nomeado do Windows)."""
    if sys.platform != "win32":
        return False
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.CreateMutexW.restype = ctypes.c_void_p
    main.mutex = k.CreateMutexW(None, False, name)  # fica aberto enquanto o app roda
    return ctypes.get_last_error() == 183  # ERROR_ALREADY_EXISTS


def main():
    if already_running():
        return
    if sys.platform == "win32":
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("CeciBot")
    qapp = QApplication(sys.argv)
    qapp.setQuitOnLastWindowClosed(False)
    qapp.setWindowIcon(QIcon(ICON))
    app = App(qapp)
    app.start()
    sys.exit(qapp.exec())


if __name__ == "__main__":
    main()
