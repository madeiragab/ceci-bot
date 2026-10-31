"""Janela da Sala Virtual: conectar, conferir agora, horário da consulta, lembretes e silêncio."""
import time

from PySide6.QtCore import Qt, QTime, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QCheckBox, QDialog, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
                               QPushButton, QTimeEdit, QVBoxLayout)

from .clock import stamp
from .texts import freshness

QSS = """
QWidget { background: #141114; color: #f1eaea; font-family: 'Segoe UI'; font-size: 10pt; }
QLabel#title { font-size: 15pt; font-weight: 700; }
QLabel#muted { color: #a8999c; }
QLabel#warn { color: #ffb4a8; }
QPushButton { background: #2a2226; border: 1px solid #4a3439; border-radius: 6px; padding: 5px 12px; }
QPushButton:hover { background: #3a2a30; border-color: #c4202c; }
QPushButton:disabled { color: #6d6366; border-color: #2f2629; }
QPushButton#primary { background: #b3141f; border-color: #d8343f; font-weight: 600; }
QPushButton#primary:hover { background: #cf1d2a; }
QLineEdit, QTimeEdit { background: #1f191c; border: 1px solid #4a3439; border-radius: 5px; padding: 3px 6px; }
QGroupBox { border: 1px solid #3a2a30; border-radius: 8px; margin-top: 12px; padding: 8px; }
QGroupBox::title { subcontrol-origin: margin; left: 10px; color: #ff6b74; }
QCheckBox::indicator { width: 14px; height: 14px; border: 1px solid #6a4a52; border-radius: 3px; background: #1f191c; }
QCheckBox::indicator:checked { background: #b3141f; border-color: #ff6b74; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 0; }
QScrollBar::handle:vertical { background: #3a2a30; border-radius: 5px; min-height: 30px; }
QScrollBar::handle:vertical:hover { background: #b3141f; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; width: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: none; }
"""
def open_url(url):
    if url:
        QDesktopServices.openUrl(QUrl(url))  # abre no seu navegador, com a sua própria sessão


def _label(text, name=None, wrap=False):
    lb = QLabel(text)
    if name:
        lb.setObjectName(name)
    lb.setWordWrap(wrap)
    return lb


def _button(text, fn, name=None):
    b = QPushButton(text)
    if name:
        b.setObjectName(name)
    b.clicked.connect(fn)
    return b


class SalaDialog(QDialog):
    """Conectar Sala Virtual: login, desconectar, consulta diária, lembretes e horário silencioso."""

    def __init__(self, sala):
        super().__init__(None, Qt.Window)
        self.sala = sala
        self.setWindowTitle("Ceci — Sala Virtual")
        self.setStyleSheet(QSS)
        self.setMinimumWidth(500)
        p = sala.store.prefs()
        v = QVBoxLayout(self)
        v.addWidget(_label("Sala Virtual", "title"))
        self.state = _label("", "muted", wrap=True)
        v.addWidget(self.state)
        conn = QGroupBox("Conexão")
        f = QFormLayout(conn)
        self.url = QLineEdit(p["url"])
        f.addRow("Endereço", self.url)
        row = QHBoxLayout()
        self.b_connect = _button("Conectar Sala Virtual", self._connect, "primary")
        self.b_check = _button("Conferir agora", lambda: sala.sync("manual"))
        self.b_off = _button("Desconectar e apagar sessão", self._disconnect)
        for b in (self.b_connect, self.b_check, self.b_off):
            row.addWidget(b)
        f.addRow(row)
        f.addRow(_label("O login abre a página oficial numa janela do Edge: você digita CPF e senha lá, a Ceci "
                        "nunca vê a senha. Ela guarda só a sessão, protegida pelo Windows.", "muted", wrap=True))
        v.addWidget(conn)
        sched = QGroupBox("Consulta automática (uma por dia)")
        f = QFormLayout(sched)
        self.auto = QTimeEdit(QTime.fromString(p["auto_time"], "HH:mm"))
        self.auto.setDisplayFormat("HH:mm")
        f.addRow("Horário (São Paulo)", self.auto)
        self.when = _label("", "muted", wrap=True)
        f.addRow(self.when)
        v.addWidget(sched)
        rem = QGroupBox("Lembretes")
        f = QFormLayout(rem)
        self.rem = {}
        grid = QHBoxLayout()
        for k, t in (("7d", "7 dias antes"), ("3d", "3 dias antes"), ("24h", "24 h antes"), ("2h", "2 h antes"),
                     ("dia", "No dia"), ("atrasada", "Atrasada")):
            c = QCheckBox(t, checked=p["remind"].get(k, True))
            self.rem[k] = c
            grid.addWidget(c)
        f.addRow(grid)
        self.toast = QCheckBox("Notificação do Windows", checked=p["toast"])
        self.ceci = QCheckBox("A Ceci avisa com animação e balão", checked=p["ceci"])
        f.addRow(self.toast)
        f.addRow(self.ceci)
        qrow = QHBoxLayout()
        self.quiet = QCheckBox("Horário silencioso de", checked=p["quiet"])
        self.q_start = QTimeEdit(QTime.fromString(p["quiet_start"], "HH:mm"))
        self.q_end = QTimeEdit(QTime.fromString(p["quiet_end"], "HH:mm"))
        for w in (self.q_start, self.q_end):
            w.setDisplayFormat("HH:mm")
        qrow.addWidget(self.quiet)
        qrow.addWidget(self.q_start)
        qrow.addWidget(QLabel("até"))
        qrow.addWidget(self.q_end)
        qrow.addStretch()
        f.addRow(qrow)
        self.u_quiet = QCheckBox("Alertas importantes (2 h antes e atraso) avisam mesmo no horário silencioso",
                                 checked=p["urgent_quiet"])
        self.u_fs = QCheckBox("Alertas importantes aparecem (só a notificação) mesmo em tela cheia",
                              checked=p["urgent_fullscreen"])
        f.addRow(self.u_quiet)
        f.addRow(self.u_fs)
        v.addWidget(rem)
        bottom = QHBoxLayout()
        bottom.addStretch()
        bottom.addWidget(_button("Salvar", self._save, "primary"))
        bottom.addWidget(_button("Fechar", self.close))
        v.addLayout(bottom)
        sala.changed.connect(self.refresh)
        sala.progress.connect(lambda _: self.refresh())
        sala.login_done.connect(self._login_done)
        self.refresh()

    def _save(self):
        url = self.url.text().strip().rstrip("/")
        if not url.startswith("https://"):
            QMessageBox.warning(self, "Sala Virtual", "O endereço precisa começar com https://")
            return
        old = self.sala.store.prefs()["url"]
        self.sala.store.set_prefs(
            url=url, auto_time=self.auto.time().toString("HH:mm"),
            remind={k: c.isChecked() for k, c in self.rem.items()}, toast=self.toast.isChecked(),
            ceci=self.ceci.isChecked(), quiet=self.quiet.isChecked(), quiet_start=self.q_start.time().toString("HH:mm"),
            quiet_end=self.q_end.time().toString("HH:mm"), urgent_quiet=self.u_quiet.isChecked(),
            urgent_fullscreen=self.u_fs.isChecked())
        if url != old and self.sala.connected():
            self.sala.disconnect()  # sessão era de outro endereço
        self.sala.reschedule()
        self.refresh()

    def _connect(self):
        self._save()
        if self.sala.connect_account():
            self.state.setText("Abrindo a página oficial de login… entre com o seu CPF e senha na janela do Edge.")

    def _disconnect(self):
        if QMessageBox.question(self, "Sala Virtual", "Desconectar e apagar a sessão salva neste computador?\n"
                                "As atividades já salvas continuam disponíveis offline.") == QMessageBox.Yes:
            self.sala.disconnect()

    def _login_done(self, ok, msg):
        self.refresh()
        if not ok:
            QMessageBox.warning(self, "Sala Virtual", msg)

    def refresh(self):
        s, now = self.sala, time.time()
        conn = s.connected()
        if s.busy == "login":
            txt = "Esperando você entrar na janela de login…"
        elif s.busy == "sync":
            txt = "Conferindo a Sala Virtual agora…"
        elif not conn:
            txt = "Não conectada."
        elif s.session_expired():
            txt = "Conectada, mas a sessão expirou: clique em Conectar Sala Virtual para entrar de novo."
        else:
            txt = "Conectada."
        fresh, _ = freshness(s.store, now)
        self.state.setText(f"{txt} {fresh}")
        self.b_connect.setText("Entrar de novo" if conn else "Conectar Sala Virtual")
        self.b_connect.setEnabled(not s.busy)
        self.b_check.setEnabled(conn and not s.busy)
        self.b_off.setEnabled(conn and not s.busy)
        auto = s.store.last_auto_day()
        ok = s.store.last_success()
        self.when.setText(f"Última tentativa automática: {auto or 'nenhuma'} · última sincronização bem-sucedida: "
                          f"{stamp(ok['finished']) if ok else 'nenhuma'}. Se o app estiver fechado no horário, a "
                          f"consulta do dia acontece quando ele abrir. Falhou? Não tenta de novo sozinha: use "
                          f"Conferir agora.")
