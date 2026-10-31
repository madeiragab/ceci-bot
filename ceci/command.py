"""Caixinha do clique duplo: você digita, a Ceci responde falando. Sem IA: só palavras-chave fixas."""
import re

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QLineEdit

from .sala.texts import norm

# ordem importa: "o que vence hoje" é hoje (não prazo); "atividades atrasadas" é atrasadas
WORDS = (
    ("ajuda", ("ajuda", "help", "comando")),
    ("atrasadas", ("atrasad",)),
    ("hoje", ("hoje",)),
    ("amanha", ("amanha",)),
    ("semana", ("semana",)),
    ("prazo", ("prazo", "proxim", "vence")),
    ("resumo", ("resumo",)),
    ("atividades", ("atividade", "tarefa", "pendent", "lista", "faculdade")),
    ("conferir", ("confer", "atualiz", "sincroniz", "checa", "verific")),
    ("conectar", ("conect", "login")),
    ("passear", ("passe", "anda", "caminha")),
    ("falar", ("fala", "conversa", "conta")),
    ("esconder", ("escond",)),
    ("configuracoes", ("config",)),
)
HELLO = {"oi", "oie", "oii", "ola", "eai", "salve", "opa"}
HELP = ["Sem IA, eu entendo umas palavras: atividades, prazo, hoje, amanhã, semana, atrasadas, resumo e conferir.",
        "\"fiz\" + um pedaço do nome marca uma atividade como feita por você; \"não fiz\" + o nome desmarca.",
        "E também: passear, fala algo, esconder, configurações, conectar."]


def parse(text):
    """(ação, resto). Ação desconhecida = "?" com o texto digitado."""
    t = norm(text).strip(" .!?")
    m = re.match(r"(?:nao|desfaz\w*|desmarca\w*)\s+(?:fiz\s+)?(.+)", t)
    if m and (t.startswith("nao fiz") or not t.startswith("nao")):
        return "desfazer", m.group(1)
    m = re.match(r"(?:ja\s+)?(?:fiz|feito|entreguei|terminei)\b\s*(.*)", t)
    if m:
        return "fiz", m.group(1)
    words = re.findall(r"\w+", t)
    for action, keys in WORDS:
        if any(w.startswith(k) for k in keys for w in words):
            return action, ""
    if words and set(words) <= HELLO | {"ceci"}:
        return "oi", ""
    return "?", text.strip()


class CommandBox(QLineEdit):
    """Campo pequeno ao lado da Ceci. Enter manda; Esc ou clicar fora fecha."""
    submitted = Signal(str)

    def __init__(self):
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setAttribute(Qt.WA_QuitOnClose, False)  # fechar a caixinha nunca fecha o app
        self.setPlaceholderText("Fala comigo: atividades, prazo, hoje, resumo… (Esc fecha)")
        self.setFixedWidth(330)
        self.setStyleSheet("QLineEdit { background: #141114; color: #f1eaea; border: 2px solid #b3141f;"
                           " border-radius: 10px; padding: 6px 10px; font-family: 'Segoe UI'; font-size: 10pt; }")
        self.returnPressed.connect(self._send)

    def _send(self):
        text = self.text().strip()
        self.close()
        if text:
            self.submitted.emit(text)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(e)

    def focusOutEvent(self, e):
        super().focusOutEvent(e)
        self.close()

    def show_beside(self, foot, scale, area):
        """Na altura da cintura dela, do lado que tiver espaço (o balão fica em cima da cabeça)."""
        self.adjustSize()
        x = foot.x() + 110 * scale
        if x + self.width() > area.right():
            x = foot.x() - 110 * scale - self.width()
        y = foot.y() - 170 * scale - self.height() / 2
        self.move(int(max(area.left(), x)), int(min(max(area.top(), y), area.bottom() - self.height())))
        self.show()
        self.activateWindow()
        self.setFocus()
