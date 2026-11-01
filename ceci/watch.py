"""Olho na tela: você troca de janela ou de aba (o título da janela da frente muda) e fica nela uns segundos →
a Ceci espia a tela e comenta. Só lê o título e o programa da janela da frente (nada de histórico, endereço ou
cookies) e deixa de fora aba anônima, senha/login, banco, e-mail, conversa e gerenciador de senha.
Opção "Espiar a tela sozinha" (auto_look).
"""
import re
import time

from PySide6.QtCore import QObject, QTimer, Signal

from . import desktop

TICK = 1000    # ms entre olhadas no título da janela da frente
STABLE = 5.0   # s na mesma aba antes de espiar (passar correndo pelas abas não conta)
GAP = 180      # s mínimos entre espiadas (cota grátis das IAs que enxergam imagem)
SEEN = 1800    # s até poder comentar de novo a mesma aba
START = 45     # s depois de abrir até a primeira espiada
SUFFIX = re.compile(r"\s+[-—–]\s+(?:Google Chrome|Mozilla Firefox|Microsoft\W*Edge|Brave|Opera(?: GX)?|Vivaldi|"
                    r"Chromium|Zen Browser|Arc|LibreWolf|Waterfox|Floorp|Yandex)\s*$", re.I)
COUNT = re.compile(r"^(?:\(\d+\+?\)|[•●*])\s*")  # "(3) YouTube": contador de notificação não é aba nova
MORE = re.compile(r"\s+(?:e mais \d+ p[aá]ginas?|and \d+ more pages?)\b.*$", re.I)
PRIVATE = re.compile(r"inprivate|incognito|an[oô]nim[ao]|navega[cç][aã]o privada|private browsing|janela privada", re.I)
SENSITIVE = re.compile(r"senha|password|login|log in|sign ?in|entrar|autentica|verifica[cç][aã]o|2fa|c[oó]digo de "
                       r"seguran|banco|bank|pix|fatura|cart[aã]o|boleto|nubank|ita[uú]|bradesco|santander|caixa|"
                       r"\binter\b|picpay|mercado pago|paypal|gov\.br|receita|whatsapp|telegram|messenger|direct|"
                       r"inbox|caixa de entrada|e-?mail|gmail|outlook|proton|mensagens", re.I)
# programas que ela nunca espia: conversa, e-mail, senhas
APPS = frozenset(("whatsapp.exe", "whatsapp.root.exe", "telegram.exe", "discord.exe", "signal.exe", "slack.exe",
                  "teams.exe", "ms-teams.exe", "outlook.exe", "olk.exe", "hxoutlook.exe", "thunderbird.exe",
                  "keepass.exe", "keepassxc.exe", "bitwarden.exe", "1password.exe", "lastpass.exe", "dashlane.exe",
                  "credentialuibroker.exe", "consent.exe", "lockapp.exe", "logonui.exe"))
BLANK = re.compile(r"^(?:nova guia|nova aba|new tab|nova janela|start page|p[aá]gina inicial|speed dial|"
                   r"untitled|sem t[ií]tulo|carregando.*|loading.*)$", re.I)


def tab_title(title):
    """Título da aba sem o nome do navegador ("Vídeo legal - YouTube - Brave" → "Vídeo legal - YouTube")."""
    t = SUFFIX.sub("", title.replace("\u200b", "")).strip()
    return COUNT.sub("", MORE.sub("", t).strip())


def private(title):
    """Aba que a Ceci não espia: anônima, senha/login, banco, e-mail, conversa, página em branco."""
    return bool(PRIVATE.search(title) or SENSITIVE.search(title) or BLANK.match(title) or not title)


class Watcher(QObject):
    tab = Signal(object)  # desktop.Win (title limpo) parada há STABLE s e digna de espiada

    def __init__(self, clock=time.monotonic, fg=desktop.foreground):
        super().__init__()
        self.now, self.fg = clock, fg
        self.cur = self.fired = None
        self.since = 0.0
        self.last = clock() - GAP + START
        self.seen = {}
        self.timer = QTimer(self, timeout=self._tick)

    def set_on(self, on):
        if on and not self.timer.isActive():
            self.cur = self.fired = None
            self.timer.start(TICK)
        elif not on:
            self.timer.stop()

    def _tick(self):
        w, now = self.fg(), self.now()
        key = (w.hwnd, w.title) if w and w.exe not in APPS else None
        if key != self.cur:
            self.cur, self.since = key, now
            return
        if not key or key == self.fired or now - self.since < STABLE:
            return
        self.fired = key  # esta aba já foi decidida (espiada ou não): só uma troca nova conta
        title = tab_title(w.title) if w.browser else COUNT.sub("", w.title.strip())
        if private(title) or now - self.last < GAP or now - self.seen.get(title, -SEEN) < SEEN:
            return
        self.last = self.seen[title] = now
        if len(self.seen) > 200:
            self.seen = {t: s for t, s in self.seen.items() if now - s < SEEN}
        w.title = title
        self.tab.emit(w)
