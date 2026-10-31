"""Janela "Abrir chat" (botão direito → Abrir chat): o histórico inteiro da mesma conversa da caixinha.

Fechar a janela não apaga nada. Respostas longas aparecem completas aqui, mesmo resumidas no balão.
"Chaves" guarda as chaves das APIs (protegidas pelo Windows, keys.py) e mostra a corrente de provedores.
"""
import html
import time

from PySide6.QtWidgets import (QDialog, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton,
                               QTextBrowser, QVBoxLayout, QWidget)

from ..sala.ui import QSS
from . import keys, latex
from .chain import SERVICES

CSS = (".u { color: #f1eaea; margin: 8px 0 0 60px; } .c { color: #f1eaea; margin: 8px 60px 0 0; }"
       " .who { color: #ff6b74; font-weight: 600; } .me { color: #a8999c; font-weight: 600; }"
       " .t { color: #8d8084; font-size: 8pt; } .s { color: #8d8084; text-align: center; margin: 10px 0; }"
       " .e { color: #ffb4a8; } pre { background: #0d0b0d; padding: 6px; }")


def _body(text):
    """Texto do modelo como veio (markdown cru), com quebras de linha e blocos de código legíveis."""
    out, code = [], False
    for part in text.split("```"):
        if code:
            out.append("<pre>" + html.escape(part.split("\n", 1)[-1] if "\n" in part else part) + "</pre>")
        else:
            out.append(html.escape(latex.render(part)).replace("\n", "<br>"))
        code = not code
    return "".join(out)


class ChatWindow(QWidget):
    def __init__(self, ai, send):
        super().__init__()
        self.ai, self.send = ai, send
        self.setWindowTitle("Chat com a Ceci")
        self.setStyleSheet(QSS)
        self.resize(460, 600)
        v = QVBoxLayout(self)
        self.status = QLabel("")
        self.status.setObjectName("muted")
        self.status.setWordWrap(True)
        v.addWidget(self.status)
        self.view = QTextBrowser()
        self.view.document().setDefaultStyleSheet(CSS)
        self.view.setStyleSheet("QTextBrowser { background: #1a1518; border: 1px solid #2f2428; border-radius: 8px;"
                                " padding: 6px; }")
        v.addWidget(self.view, 1)
        row = QHBoxLayout()
        self.input = QLineEdit()
        self.input.setPlaceholderText("Escreve aqui (é a mesma conversa da caixinha)")
        self.input.returnPressed.connect(self._send)
        row.addWidget(self.input, 1)
        b = QPushButton("Enviar")
        b.setObjectName("primary")
        b.clicked.connect(self._send)
        row.addWidget(b)
        v.addLayout(row)
        row = QHBoxLayout()
        for label, fn in (("Nova conversa", ai.reset), ("Apagar histórico", self._clear), ("Chaves", self._keys)):
            b = QPushButton(label)
            b.clicked.connect(fn)
            row.addWidget(b)
        row.addStretch(1)
        v.addLayout(row)
        ai.changed.connect(self.refresh)
        self.refresh()

    def _send(self):
        t = self.input.text().strip()
        self.input.clear()
        if t:
            self.send(t)

    def _keys(self):
        KeysDialog(self.ai.provider, self).exec()
        self.refresh()

    def _clear(self):
        if QMessageBox.question(self, "Apagar histórico", "Apagar toda a conversa guardada?") == QMessageBox.Yes:
            self.ai.reset()
            self.ai.conv.clear()
            self.refresh()

    def refresh(self):
        ok, why = self.ai.provider.is_available()
        lines = getattr(self.ai.provider, "describe", lambda: [])() if ok else []
        self.status.setText(f"IA: {self.ai.provider.name}" + ("" if ok else f" (desligada: {why})")
                            + "".join("\n• " + x for x in lines))
        parts = []
        for m in self.ai.conv.messages:
            when = time.strftime("%d/%m %H:%M", time.localtime(m["at"]))
            if m["role"] == "sistema":
                parts.append(f"<p class='s'>— {html.escape(m['text'])} · {when} —</p>")
            elif m["role"] == "user":
                parts.append(f"<p class='u'><span class='me'>Você</span> <span class='t'>{when}</span><br>"
                             f"{_body(m['text'])}</p>")
            else:
                cls = " e" if m.get("error") else ""
                cut = "<br><i class='t'>(resposta cortada)</i>" if m.get("complete") is False else ""
                by = f" · {html.escape(m['provider'])}" if m.get("provider") else ""
                parts.append(f"<p class='c{cls}'><span class='who'>Ceci</span> <span class='t'>{when}{by}</span><br>"
                             f"{_body(m['text'])}{cut}</p>")
        self.view.setHtml("".join(parts) or "<p class='s'>Nada por aqui ainda. Clique duplo na Ceci e digita.</p>")
        sb = self.view.verticalScrollBar()
        sb.setValue(sb.maximum())


class KeysDialog(QDialog):
    """Uma chave por serviço, na ordem da corrente. O campo nunca mostra a chave salva."""

    def __init__(self, provider, parent=None):
        super().__init__(parent)
        self.provider = provider
        self.setWindowTitle("Chaves das IAs")
        self.setStyleSheet(QSS)
        v = QVBoxLayout(self)
        info = QLabel("A Ceci tenta na ordem abaixo e passa para a próxima quando uma bate no limite. "
                      "As chaves ficam neste PC, protegidas pelo Windows, e cada uma só vai para o próprio serviço.")
        info.setObjectName("muted")
        info.setWordWrap(True)
        v.addWidget(info)
        grid = QGridLayout()
        saved = keys.load()
        self.fields = {}
        for row, (service, (label, _, _, _, where)) in enumerate(SERVICES.items()):
            grid.addWidget(QLabel(label), row, 0)
            f = QLineEdit()
            f.setEchoMode(QLineEdit.Password)
            f.setPlaceholderText("salva (cole outra para trocar)" if service in saved else f"cole a chave · {where}")
            grid.addWidget(f, row, 1)
            b = QPushButton("Apagar")
            b.setEnabled(service in saved)
            b.clicked.connect(lambda _=False, s=service: self._drop(s))
            grid.addWidget(b, row, 2)
            self.fields[service] = (f, b)
        v.addLayout(grid)
        row = QHBoxLayout()
        row.addStretch(1)
        ok = QPushButton("Salvar")
        ok.setObjectName("primary")
        ok.clicked.connect(self._save)
        row.addWidget(ok)
        close = QPushButton("Fechar")
        close.clicked.connect(self.reject)
        row.addWidget(close)
        v.addLayout(row)
        self.resize(560, 0)

    def _changed(self, service):
        if hasattr(self.provider, "forget"):
            self.provider.forget(service)

    def _drop(self, service):
        keys.put(service, "")
        self._changed(service)
        f, b = self.fields[service]
        f.clear()
        f.setPlaceholderText("cole a chave · " + SERVICES[service][4])
        b.setEnabled(False)

    def _save(self):
        for service, (f, _) in self.fields.items():
            if f.text().strip():
                keys.put(service, f.text())
                self._changed(service)
        self.accept()
