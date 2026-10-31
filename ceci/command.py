"""Caixinha do clique duplo: você digita, a Ceci responde falando (o roteador decide comando ou conversa)."""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QLineEdit


HELP = ["Comandos (não usam IA): atividades, atrasadas, hoje, amanhã, semana, prazo, resumo, conferir.",
        "\"fiz\" + nome marca como feita por você; \"não fiz\" + nome desmarca; \"abre a atividade de\" + "
        "disciplina abre no navegador.",
        "Também: abre o chat, abre as configurações, fica quietinha, vai dormir, vai passear, para, tenta de novo, "
        "nova conversa.",
        "O resto vira conversa com a IA, quando tiver uma conectada."]


class CommandBox(QLineEdit):
    """Barrinha ao lado da Ceci. Enter manda; Esc ou clicar fora some."""
    submitted = Signal(str)

    def __init__(self):
        super().__init__()
        # barrinha solta: sem moldura, sem X, sem botão na barra de tarefas, quase transparente
        self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setAttribute(Qt.WA_QuitOnClose, False)  # fechar a caixinha nunca fecha o app
        self.setPlaceholderText("fala comigo…")
        self.setFixedWidth(260)
        self.setStyleSheet("QLineEdit { background: rgba(20, 17, 20, 70); color: #ffffff; border: 1px solid"
                           " rgba(255, 255, 255, 60); border-radius: 9px; padding: 4px 10px;"
                           " font-family: 'Segoe UI'; font-size: 10pt; selection-background-color: #b3141f; }")
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
