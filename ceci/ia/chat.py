"""Janela "Abrir chat" (botão direito → Abrir chat): o histórico inteiro da mesma conversa da caixinha.

Fechar a janela não apaga nada. Respostas longas aparecem completas aqui, mesmo resumidas no balão.
"""
import html
import time

from PySide6.QtWidgets import (QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QTextBrowser, QVBoxLayout,
                               QWidget)

from ..sala.ui import QSS

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
            out.append(html.escape(part).replace("\n", "<br>"))
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
        for label, fn in (("Nova conversa", ai.reset), ("Apagar histórico", self._clear)):
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

    def _clear(self):
        if QMessageBox.question(self, "Apagar histórico", "Apagar toda a conversa guardada?") == QMessageBox.Yes:
            self.ai.reset()
            self.ai.conv.clear()
            self.refresh()

    def refresh(self):
        ok, why = self.ai.provider.is_available()
        self.status.setText(f"IA: {self.ai.provider.name}" + ("" if ok else f" (desligada: {why})"))
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
                parts.append(f"<p class='c{cls}'><span class='who'>Ceci</span> <span class='t'>{when}</span><br>"
                             f"{_body(m['text'])}{cut}</p>")
        self.view.setHtml("".join(parts) or "<p class='s'>Nada por aqui ainda. Clique duplo na Ceci e digita.</p>")
        sb = self.view.verticalScrollBar()
        sb.setValue(sb.maximum())
