"""Janelas da Sala Virtual: configurações/conexão, Minhas atividades, Resumo da faculdade e o cartão de aviso."""
import time

from PySide6.QtCore import QPoint, Qt, QTime, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QFormLayout, QFrame, QGroupBox, QHBoxLayout, QLabel,
                               QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPushButton, QTextBrowser,
                               QTimeEdit, QVBoxLayout, QWidget)

from .clock import stamp
from .store import STATUS_LABEL, status
from .texts import TODO, course, freshness, info, sort_key, summary_html

RED, AMBER, GREEN, GRAY, VIOLET, BLUE = "#ff4d5a", "#e8a23a", "#4fbf7f", "#9a8f92", "#b68cff", "#6fa8dc"
COLOR = {"atrasada": RED, "pendente": AMBER, "desconhecido": AMBER, "entregue": GREEN, "concluida": GREEN,
         "manual": VIOLET, "evento": BLUE, "sem_prazo": GRAY, "indisponivel": GRAY, "passado": GRAY}
QSS = """
QWidget { background: #141114; color: #f1eaea; font-family: 'Segoe UI'; font-size: 10pt; }
QLabel#title { font-size: 15pt; font-weight: 700; }
QLabel#muted, QLabel#course { color: #a8999c; }
QLabel#course { color: #ff6b74; font-size: 8.5pt; font-weight: 600; }
QLabel#warn { color: #ffb4a8; }
QLabel#name { font-weight: 600; }
QPushButton { background: #2a2226; border: 1px solid #4a3439; border-radius: 6px; padding: 5px 12px; }
QPushButton:hover { background: #3a2a30; border-color: #c4202c; }
QPushButton:disabled { color: #6d6366; border-color: #2f2629; }
QPushButton#primary { background: #b3141f; border-color: #d8343f; font-weight: 600; }
QPushButton#primary:hover { background: #cf1d2a; }
QPushButton#small { padding: 2px 9px; font-size: 9pt; }
QComboBox, QLineEdit, QTimeEdit { background: #1f191c; border: 1px solid #4a3439; border-radius: 5px; padding: 3px 6px; }
QComboBox QAbstractItemView { background: #1f191c; selection-background-color: #b3141f; }
QListWidget { background: #141114; border: none; outline: none; }
QListWidget::item, QListWidget::item:selected, QListWidget::item:hover { background: transparent; }
QFrame#row { background: #1d171a; border: 1px solid #2f2428; border-radius: 8px; }
QFrame#row QLabel, QFrame#chip QLabel, QFrame#card QLabel { background: transparent; }
QFrame#chip { background: #1f191c; border: 1px solid #3a2a30; border-radius: 8px; }
QGroupBox { border: 1px solid #3a2a30; border-radius: 8px; margin-top: 12px; padding: 8px; }
QGroupBox::title { subcontrol-origin: margin; left: 10px; color: #ff6b74; }
QTextBrowser { background: #1a1518; border: 1px solid #2f2428; border-radius: 8px; padding: 6px; }
QCheckBox::indicator { width: 14px; height: 14px; border: 1px solid #6a4a52; border-radius: 3px; background: #1f191c; }
QCheckBox::indicator:checked { background: #b3141f; border-color: #ff6b74; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 0; }
QScrollBar::handle:vertical { background: #3a2a30; border-radius: 5px; min-height: 30px; }
QScrollBar::handle:vertical:hover { background: #b3141f; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; width: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: none; }
"""
SUMMARY_CSS = ("h3 { color: #ff6b74; margin: 12px 0 4px 0; } ul { margin: 0; } li { margin-bottom: 5px; }"
               " a { color: #ffd9dc; font-weight: 600; } .m { color: #a8999c; } .w { color: #ffb4a8; }")
FILTERS = (("A fazer", TODO), ("Todas", None), ("Pendentes", ("pendente", "desconhecido")), ("Atrasadas", ("atrasada",)),
           ("Entregues (confirmado pelo Moodle)", ("entregue",)), ("Concluídas (critério do Moodle)", ("concluida",)),
           ("Sem prazo definido", ("sem_prazo",)), ("Marcadas por mim", ("manual",)), ("Eventos", ("evento", "passado")),
           ("Indisponíveis", ("indisponivel",)))


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


class Row(QFrame):
    """Uma atividade: barra de cor pela urgência, disciplina, nome, prazo, status e botões."""

    def __init__(self, r, now, on_manual):
        super().__init__()
        self.setObjectName("row")
        st = status(r, now)
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 8, 0)
        bar = QFrame()
        dl = r["due"] or r["close"] or r["expected"]
        hot = st in ("pendente", "desconhecido", "evento") and dl and dl - now < 86400
        bar.setFixedWidth(5)
        bar.setStyleSheet(f"background: {RED if hot else COLOR.get(st, GRAY)}; border-radius: 2px;")
        h.addWidget(bar)
        v = QVBoxLayout()
        v.setContentsMargins(6, 6, 0, 6)
        v.setSpacing(1)
        v.addWidget(_label(course(r).upper(), "course"))
        name = _label(r["name"], "name", wrap=True)
        v.addWidget(name)
        v.addWidget(_label(info(r, now), "muted", wrap=True))
        badge = _label(STATUS_LABEL[st])
        badge.setStyleSheet(f"color: {COLOR.get(st, GRAY)}; font-size: 9pt; font-weight: 600;")
        v.addWidget(badge)
        h.addLayout(v, 1)
        col = QVBoxLayout()
        col.setSpacing(4)
        op = _button("Abrir", lambda: open_url(r["url"]), "small")
        op.setEnabled(bool(r["url"]))
        op.setToolTip("Abrir esta atividade na Sala Virtual")
        col.addWidget(op)
        if st not in ("entregue", "concluida", "passado", "indisponivel"):
            mk = _button("Desmarcar" if r["manual"] else "Já fiz", lambda: on_manual(r["key"], not r["manual"]), "small")
            mk.setToolTip("Só para você: NÃO conta como entrega confirmada pelo Moodle")
            col.addWidget(mk)
        col.addStretch()
        h.addLayout(col)


class ActivitiesWindow(QWidget):
    def __init__(self, sala, on_summary):
        super().__init__(None, Qt.Window)
        self.sala = sala
        self.setWindowTitle("Ceci — Minhas atividades")
        self.setStyleSheet(QSS)
        self.resize(580, 680)
        v = QVBoxLayout(self)
        v.addWidget(_label("Minhas atividades", "title"))
        self.fresh = _label("", "muted", wrap=True)
        v.addWidget(self.fresh)
        chips = QHBoxLayout()
        self.chip_pend, self.chip_late, self.chip_next = (QLabel(), QLabel(), QLabel())
        for lb in (self.chip_pend, self.chip_late, self.chip_next):
            f = QFrame()
            f.setObjectName("chip")
            lay = QVBoxLayout(f)
            lay.setContentsMargins(10, 6, 10, 6)
            lb.setWordWrap(True)
            lay.addWidget(lb)
            chips.addWidget(f, 2 if lb is self.chip_next else 1)
        v.addLayout(chips)
        flt = QHBoxLayout()
        self.f_course, self.f_status = QComboBox(), QComboBox()
        for t, _ in FILTERS:
            self.f_status.addItem(t)
        flt.addWidget(_label("Disciplina", "muted"))
        flt.addWidget(self.f_course, 2)
        flt.addWidget(_label("Status", "muted"))
        flt.addWidget(self.f_status, 1)
        v.addLayout(flt)
        self.list = QListWidget()
        self.list.setSpacing(3)
        self.list.setVerticalScrollMode(QListWidget.ScrollPerPixel)
        self.list.setSelectionMode(QListWidget.NoSelection)
        v.addWidget(self.list, 1)
        bottom = QHBoxLayout()
        self.check = _button("Conferir agora", self._check, "primary")
        bottom.addWidget(self.check)
        bottom.addWidget(_button("Resumo da faculdade", on_summary))
        bottom.addStretch()
        bottom.addWidget(_button("Fechar", self.close))
        v.addLayout(bottom)
        self.f_course.currentIndexChanged.connect(self._fill)
        self.f_status.currentIndexChanged.connect(self._fill)
        sala.changed.connect(self.refresh)
        sala.progress.connect(lambda _: self._busy(True))
        sala.finished.connect(lambda _: self._busy(False))
        self.refresh()

    def _check(self):
        if not self.sala.connected():
            QMessageBox.information(self, "Sala Virtual", "Conecte a Sala Virtual em Configurações primeiro.")
            return
        self.sala.sync("manual")

    def _busy(self, on):
        self.check.setEnabled(not on)
        self.check.setText("Conferindo…" if on else "Conferir agora")

    def refresh(self):
        if not self.isVisible() and self.list.count():
            return
        now = time.time()
        self.rows = [dict(r) for r in self.sala.store.rows()]
        cur = self.f_course.currentData()
        self.f_course.blockSignals(True)
        self.f_course.clear()
        self.f_course.addItem("Todas", None)
        for c in self.sala.store.courses():
            if not c["past"] or any(r["course"] == c["id"] for r in self.rows):
                self.f_course.addItem(c["name"], c["id"])
        i = self.f_course.findData(cur)
        self.f_course.setCurrentIndex(max(0, i))
        self.f_course.blockSignals(False)
        st = [status(r, now) for r in self.rows]
        pend, late = sum(s in ("pendente", "desconhecido") for s in st), st.count("atrasada")
        nxt = sorted((r for r, s in zip(self.rows, st) if s in ("pendente", "desconhecido") and (r["due"] or r["close"])),
                     key=lambda r: r["due"] or r["close"])
        self.chip_pend.setText(f"<b style='font-size:15pt'>{pend}</b><br><span style='color:#a8999c'>pendentes</span>")
        self.chip_late.setText(f"<b style='font-size:15pt;color:{RED if late else '#f1eaea'}'>{late}</b><br>"
                               f"<span style='color:#a8999c'>atrasadas</span>")
        if nxt:
            r = nxt[0]
            self.chip_next.setText(f"<span style='color:#a8999c'>Próxima entrega</span><br><b>{r['name']}</b><br>"
                                   f"<span style='color:#a8999c'>{info(r, now).split(' · ', 1)[1]}</span>")
        else:
            self.chip_next.setText("<span style='color:#a8999c'>Próxima entrega</span><br>nenhuma pendente")
        fresh, warn = freshness(self.sala.store, now)
        if not self.sala.connected():
            fresh, warn = "Sala Virtual não conectada (Configurações → Conectar Sala Virtual). " + fresh, True
        self.fresh.setText(fresh)
        self.fresh.setObjectName("warn" if warn else "muted")
        self.fresh.setStyleSheet("")
        self._fill()

    def _fill(self):
        now = time.time()
        cid, want = self.f_course.currentData(), FILTERS[self.f_status.currentIndex()][1]
        self.list.clear()
        rows = [r for r in getattr(self, "rows", []) if (cid is None or r["course"] == cid)
                and (want is None or status(r, now) in want)]
        last = self.sala.store.last_success()
        for r in sorted(rows, key=lambda r: sort_key(r, now)):
            if last and r["last_seen"] and r["last_seen"] < last["started"]:
                r = {**r, "name": f"{r['name']}  (dados de {stamp(r['last_seen'])})"}
            it = QListWidgetItem()
            w = Row(r, now, self._manual)
            it.setSizeHint(w.sizeHint())
            self.list.addItem(it)
            self.list.setItemWidget(it, w)
        if not rows:
            self.list.addItem(QListWidgetItem("Nada por aqui com esses filtros."))

    def _manual(self, key, on):
        self.sala.store.set_manual(key, on)
        self.refresh()

    def showEvent(self, e):
        super().showEvent(e)
        self.refresh()


class SummaryDialog(QDialog):
    def __init__(self, sala):
        super().__init__(None, Qt.Window)
        self.sala = sala
        self.setWindowTitle("Ceci — Resumo da faculdade")
        self.setStyleSheet(QSS)
        self.resize(520, 600)
        v = QVBoxLayout(self)
        v.addWidget(_label("Resumo da faculdade", "title"))
        self.view = QTextBrowser()
        self.view.setOpenExternalLinks(True)
        self.view.document().setDefaultStyleSheet(SUMMARY_CSS)
        v.addWidget(self.view, 1)
        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(_button("Fechar", self.close))
        v.addLayout(row)
        sala.changed.connect(self.refresh)
        self.refresh()

    def refresh(self):
        self.view.setHtml(summary_html(self.sala.store, time.time()))


class AlertCard(QWidget):
    """Cartão perto da Ceci com os avisos e o botão para abrir cada atividade no Moodle."""

    def __init__(self, items, now, title, on_list):
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setStyleSheet(QSS + "QWidget#card { border: 1px solid #b3141f; border-radius: 10px; }")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        card = QFrame()
        card.setObjectName("card")
        outer.addWidget(card)
        v = QVBoxLayout(card)
        head = QHBoxLayout()
        head.addWidget(_label(f"<b>{title}</b>"), 1)
        head.addWidget(_button("✕", self.close, "small"))
        v.addLayout(head)
        for i in items[:5]:
            r = i["row"]
            f = QFrame()
            f.setObjectName("row")
            h = QHBoxLayout(f)
            col = QVBoxLayout()
            col.setSpacing(1)
            col.addWidget(_label(course(r).upper(), "course"))
            col.addWidget(_label(r["name"], "name", wrap=True))
            col.addWidget(_label(info(r, now), "muted", wrap=True))
            h.addLayout(col, 1)
            op = _button("Abrir no Moodle", lambda _=False, u=r["url"]: open_url(u), "small")
            op.setEnabled(bool(r["url"]))
            h.addWidget(op)
            v.addWidget(f)
        foot = QHBoxLayout()
        if len(items) > 5:
            foot.addWidget(_label(f"+{len(items) - 5} outros", "muted"))
        foot.addStretch()
        foot.addWidget(_button("Minhas atividades", lambda: (on_list(), self.close())))
        foot.addWidget(_button("Ok", self.close, "primary"))
        v.addLayout(foot)
        self.setFixedWidth(400)
        urgent = any(i["tier"] in ("2h", "atrasada", "24h", "dia") for i in items)
        self.life = QTimer(self, singleShot=True, timeout=self.close)  # morre junto com o cartão
        self.life.start((180 if urgent else 75) * 1000)

    def show_near(self, foot, area):
        self.adjustSize()
        x = int(foot.x() - self.width() - 40)
        if x < area.left() + 8:
            x = int(foot.x() + 60)
        y = int(min(foot.y() - self.height() - 20, area.bottom() - self.height() - 8))
        self.move(QPoint(max(area.left() + 8, min(x, area.right() - self.width() - 8)), max(area.top() + 8, y)))
        self.show()


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


def screen_area(win):
    sc = QGuiApplication.screenAt(win.geometry().center()) or QGuiApplication.primaryScreen()
    return sc.availableGeometry()
