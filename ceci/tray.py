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
        for t, v in (("Mínima", 0.25), ("Pequena", 0.4), ("Média", 0.55), ("Grande", 0.75), ("Enorme", 1.0)):
            size.addAction(t, lambda v=v: app.set_size(v))
    if getattr(app, "sala", None):
        m.addSeparator()
        m.addAction("Olhar minha tela (Ctrl+Alt+C)", app.look_screen)
        m.addAction("Minhas atividades", app.tell_activities)
        m.addAction("Resumo da faculdade", app.tell_summary)
        m.addAction("Conferir Sala Virtual agora", app.check_sala)
        m.addAction("Abrir chat", app.open_chat)
        m.addSeparator()
    for text, key, on, slot in (("Pausar animações", "pause", app.win.player.paused, app.set_paused),
                                ("Sentar nas janelas", "perch", app.s["perch"], app.set_perch),
                                ("Espiar a tela sozinha", "auto_look", app.s["auto_look"], app.set_auto_look)):
        act = QAction(text, m, checkable=True, checked=bool(on))
        act.setData(key)
        act.toggled.connect(slot)
        m.addAction(act)
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
        on = {"pause": self.app.win.player.paused, "perch": self.app.s["perch"], "auto_look": self.app.s["auto_look"]}
        for a in self.menu.actions():
            if a.isCheckable() and a.data() in on:
                a.blockSignals(True)
                a.setChecked(bool(on[a.data()]))
                a.blockSignals(False)

    def _activated(self, reason):
        if reason == QSystemTrayIcon.Trigger:
            self.app.hide_ceci() if self.app.win.isVisible() else self.app.show_ceci()
