"""Atalho global do Windows (funciona com qualquer programa na frente): RegisterHotKey + WM_HOTKEY."""
import ctypes
import sys
from ctypes import wintypes

from PySide6.QtCore import QAbstractNativeEventFilter, QObject, Signal

MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_NOREPEAT = 0x1, 0x2, 0x4, 0x4000
WM_HOTKEY = 0x0312


class Hotkey(QObject, QAbstractNativeEventFilter):
    pressed = Signal()

    def __init__(self, app, key="C", mods=MOD_CONTROL | MOD_ALT, ident=0xCEC1):
        QObject.__init__(self)
        QAbstractNativeEventFilter.__init__(self)
        self.app, self.ident = app, ident
        self.ok = False
        if sys.platform != "win32":
            return
        self.ok = bool(ctypes.windll.user32.RegisterHotKey(None, ident, mods | MOD_NOREPEAT, ord(key)))
        if self.ok:
            app.installNativeEventFilter(self)

    def nativeEventFilter(self, event_type, message):
        if event_type in (b"windows_generic_MSG", "windows_generic_MSG"):
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == WM_HOTKEY and msg.wParam == self.ident:
                self.pressed.emit()
                return True, 0
        return False, 0

    def close(self):
        if self.ok:
            ctypes.windll.user32.UnregisterHotKey(None, self.ident)
            self.app.removeNativeEventFilter(self)
            self.ok = False
