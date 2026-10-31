"""Janela de configurações e painel de teste de animações."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout,
                               QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton, QSlider,
                               QSpinBox, QVBoxLayout)

from .settings import set_autostart

BOOLS = [("walk", "Permitir movimentação automática"), ("follow_mouse", "Acompanhar o mouse com os olhos"),
         ("petting", "Carinho na cabeça"), ("specials", "Animações especiais automáticas"),
         ("always_on_top", "Sempre visível (acima das janelas)"), ("autostart", "Inicializar com o Windows"),
         ("pause_fullscreen", "Pausar durante jogos/apps em tela cheia"), ("eco", "Modo econômico"),
         ("breathe", "Respiração sutil quando parada"),
         ("door_entrance", "Entrar pela porta ao abrir"), ("speech", "Falas no balão")]


class SettingsDialog(QDialog):
    def __init__(self, settings, on_apply, parent=None, sala=None):
        super().__init__(parent)
        self.setWindowTitle("Ceci — Configurações")
        self.s, self.on_apply = settings, on_apply
        f = QFormLayout(self)
        self.size = QDoubleSpinBox(minimum=0.25, maximum=1.5, singleStep=0.05, value=settings["size"])
        self.speed = QDoubleSpinBox(minimum=0.25, maximum=3.0, singleStep=0.1, value=settings["speed"])
        self.fps = QSpinBox(minimum=10, maximum=60, value=settings["fps"])
        self.freq = QDoubleSpinBox(minimum=0.2, maximum=3.0, singleStep=0.1, value=settings["random_freq"])
        self.talk = QDoubleSpinBox(minimum=0.2, maximum=3.0, singleStep=0.1, value=settings["speech_freq"])
        self.pos = QComboBox()
        for k, t in (("bottom_right", "Canto inferior direito"), ("bottom_left", "Canto inferior esquerdo"),
                     ("saved", "Última posição")):
            self.pos.addItem(t, k)
        self.pos.setCurrentIndex(self.pos.findData(settings["start_pos"]))
        f.addRow("Tamanho da personagem", self.size)
        f.addRow("Velocidade das animações", self.speed)
        f.addRow("FPS (movimento/transições)", self.fps)
        f.addRow("Frequência das animações aleatórias", self.freq)
        f.addRow("Frequência das falas", self.talk)
        f.addRow("Posição inicial", self.pos)
        self.checks = {}
        for k, t in BOOLS:
            c = QCheckBox(t, checked=settings[k])
            self.checks[k] = c
            f.addRow(c)
        if sala:  # (texto do botão, abrir) — Fase 2
            b = QPushButton(sala[0])
            b.clicked.connect(sala[1])
            f.addRow("Sala Virtual", b)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Apply | QDialogButtonBox.Cancel)
        bb.accepted.connect(lambda: (self.apply(), self.accept()))
        bb.rejected.connect(self.reject)
        bb.button(QDialogButtonBox.Apply).clicked.connect(self.apply)
        f.addRow(bb)

    def apply(self):
        s = self.s
        auto_changed = s["autostart"] != self.checks["autostart"].isChecked()
        s.update(size=round(self.size.value(), 2), speed=self.speed.value(), fps=self.fps.value(),
                 random_freq=self.freq.value(), speech_freq=self.talk.value(), start_pos=self.pos.currentData(),
                 **{k: c.isChecked() for k, c in self.checks.items()})
        if auto_changed:
            set_autostart(s["autostart"])
        s.save()
        self.on_apply()


class AnimPanel(QDialog):
    """Testa cada animação na própria Ceci."""

    def __init__(self, win, behavior, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Ceci — Animações")
        self.win, self.beh, self.p = win, behavior, win.player
        self.resize(460, 560)
        v = QVBoxLayout(self)
        self.list = QListWidget()
        anims = win.sprites.anims
        for aid, a in anims.items():
            missing = [f"{st[0]}:{st[1]}" for st in a["seq"]
                       if st[0] and win.sprites.info(st[0], st[1]) is None]
            n = len({(st[0], st[1]) for st in a["seq"] if st[0]})
            sheet = a.get("sheet", "-")
            txt = f"[{a['cat']}] {a['name']}  — id={aid}  sheet={sheet}  quadros={n}"
            if a.get("catalog"):
                txt += f"  ({a['catalog']})"
            if missing:
                txt += f"  FALTANDO: {', '.join(missing)}"
            it = QListWidgetItem(txt)
            it.setData(Qt.UserRole, aid)
            self.list.addItem(it)
        self.list.itemDoubleClicked.connect(lambda _: self.play())
        v.addWidget(self.list)
        self.info = QLabel()
        v.addWidget(self.info)
        row = QHBoxLayout()
        for t, fn in (("▶ Reproduzir", self.play), ("⏸ Pausar", self.pause), ("⟲ Reiniciar", self.p.restart),
                      ("◀", lambda: self.p.step(-1)), ("▶|", lambda: self.p.step(1)), ("Idle", self.idle)):
            b = QPushButton(t)
            b.clicked.connect(fn)
            row.addWidget(b)
        v.addLayout(row)
        row2 = QHBoxLayout()
        self.loop = QCheckBox("Loop")
        self.loop.toggled.connect(lambda on: setattr(self.p, "loop_override", True if on else None))
        row2.addWidget(self.loop)
        row2.addWidget(QLabel("Velocidade"))
        self.speed = QSlider(Qt.Horizontal, minimum=25, maximum=300, value=int(win.settings["speed"] * 100))
        self.speed.valueChanged.connect(lambda val: win.settings.__setitem__("speed", val / 100))
        row2.addWidget(self.speed)
        v.addLayout(row2)
        self.p.frame.connect(self._frame)

    def _frame(self, st, _new):
        a = self.p.current
        if a and self.isVisible():
            self.info.setText(f"{self.p.aid}: passo {self.p.i + 1}/{len(a['seq'])}  "
                              f"(sheet {st[0]}, quadro {st[1]}, {st[2]} ms)")

    def play(self):
        it = self.list.currentItem()
        if it:
            self.beh.stop()
            self.win.stop_walk()
            self.p.paused = False
            aid = it.data(Qt.UserRole)
            if aid == "caminhar":  # caminhada de verdade, andando pela tela
                a, w = self.win.area(), self.win
                w.walk_to(w.foot.x() + (250 if w.foot.x() < a.center().x() else -250) * w.sprites.scale / 0.55)
            else:
                w = self.win
                w.play(aid, force=True, talk=True)

    def pause(self):
        self.p.set_paused(not self.p.paused)

    def idle(self):
        self.p.loop_override = None
        self.loop.setChecked(False)
        self.p.paused = False
        self.win.play("idle", force=True)

    def closeEvent(self, e):
        self.p.frame.disconnect(self._frame)
        self.idle()
        self.beh.schedule()
        super().closeEvent(e)
