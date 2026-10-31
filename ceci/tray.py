"""Ícone na bandeja e menu (o mesmo menu serve de menu de contexto)."""
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QMenu, QSystemTrayIcon


def build_menu(app, tray=False):
    m = QMenu()
    if tray:
        m.addAction("Mostrar", app.show_ceci)
        m.addAction("Ocultar", app.hide_ceci)
    else:
        m.addAction("Interagir", app.interact)
        m.addAction("Falar algo", app.chat)
        m.addAction("Passear", app.stroll)
        m.addAction("Ver animações", app.open_panel)
        corner = m.addMenu("Mover para outro canto")
        corner.addAction("Canto inferior direito", lambda: app.win.move_to_corner("right"))
        corner.addAction("Canto inferior esquerdo", lambda: app.win.move_to_corner("left"))
        size = m.addMenu("Alterar tamanho")
        for t, v in (("Pequena", 0.4), ("Média", 0.55), ("Grande", 0.75), ("Enorme", 1.0)):
            size.addAction(t, lambda v=v: app.set_size(v))
    pause = QAction("Pausar animações", m, checkable=True, checked=app.win.player.paused)
    pause.toggled.connect(app.set_paused)
    m.addAction(pause)
    m.addAction("Configurações", app.open_settings)
    if not tray:
        m.addAction("Ocultar", app.hide_ceci)
    m.addSeparator()
    m.addAction("Sair", app.quit_animated)
    return m


class Tray(QSystemTrayIcon):
    def __init__(self, app, icon_path):
        super().__init__(QIcon(icon_path))
        self.app = app
        self.setToolTip("Ceci Bot")
        self.activated.connect(self._activated)
        self.aboutToShow()
        self.show()

    def aboutToShow(self):
        self.menu = build_menu(self.app, tray=True)
        self.menu.aboutToShow.connect(self._refresh)
        self.setContextMenu(self.menu)

    def _refresh(self):
        for a in self.menu.actions():
            if a.isCheckable():
                a.setChecked(self.app.win.player.paused)

    def _activated(self, reason):
        if reason == QSystemTrayIcon.Trigger:
            self.app.hide_ceci() if self.app.win.isVisible() else self.app.show_ceci()
