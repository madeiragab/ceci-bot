"""Cérebro da Ceci: as falas soltas e as vontades dela vêm da IA, não só do falas.json.

De tempos em tempos (ao abrir, a cada REFRESH e depois de uma conversa) faz UM pedido à corrente: falas novas
para cada situação (parada, lendo, tomando café, sendo arrastada...) e o que ela tá com vontade de fazer agora,
com a data e a hora do PC, o humor e a conversa recente. As falas entram no lugar das prontas (que continuam de
reserva); as vontades deixam essas animações mais prováveis na rotina. Guardado em mente_ia.json.
"""
import json
import os
import re
import threading
import time

from PySide6.QtCore import QObject, QTimer, Signal

from ..sala import texts
from ..settings import CONFIG_DIR
from . import prompts
from .provider import AIError, Prompt

PATH = os.path.join(CONFIG_DIR, "mente_ia.json")
REFRESH = 40 * 60      # s entre pedidos
AFTER_CHAT = 8 * 60    # depois de uma conversa, renova se o último pedido tem mais que isso
FIRST = 15             # s depois de abrir
MAX_LEN = 140
# situação (categoria do falas.json) → o que tá acontecendo, quantas falas pedir
CATS = {
    "inicio": ("acabou de aparecer na tela do PC", 2),
    "idle": ("tá parada na tela, nada acontecendo", 6),
    "curiosa": ("reparou em algo / tá de olho no mouse", 2),
    "clique": ("o usuário clicou nela", 3),
    "carinho": ("o usuário tá fazendo carinho na cabeça dela", 2),
    "arrastada": ("tá sendo arrastada pelo mouse", 2),
    "solta": ("acabou de ser solta depois de arrastada", 2),
    "girando": ("tá sendo girada no ar pelo mouse", 2),
    "tonta": ("ficou tonta depois de girar", 2),
    "esperando": ("o usuário sumiu faz um tempo", 3),
    "lendo": ("tá lendo um livro", 2),
    "cafe": ("tá tomando café", 2),
    "sonolenta": ("tá com sono", 2),
    "dormindo": ("tá cochilando (fala dormindo, meio sem sentido)", 2),
    "acordando": ("acabou de acordar", 2),
    "espreguicando": ("tá se espreguiçando", 2),
    "feliz": ("ficou feliz", 2),
    "confusa": ("ficou confusa", 2),
    "assustada": ("levou um susto", 2),
    "brava": ("ficou brava", 2),
    "triste": ("ficou triste", 2),
    "gato": ("tá brincando com o Ozzy ou o Bowie", 2),
    "interessante": ("tá pensando / programando / mexendo em algo", 2),
    "comemorando": ("algo deu certo", 2),
    "deu_errado": ("algo deu errado / quebrou", 2),
    "conversando": ("puxando assunto do nada", 4),
    "chamando": ("chamando a atenção do usuário", 2),
    "escondendo": ("se escondendo atrás da borda da tela", 2),
    "saida": ("indo embora (o app vai fechar)", 2),
    "raras": ("fala rara, aleatória e inesperada", 3),
}
DAYS = ("segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo")


def part_of_day(h):
    return "madrugada" if h < 5 else "manhã" if h < 12 else "tarde" if h < 18 else "noite"


def now_text(ts=None):
    """Data e hora do PC, do jeito que vai para o modelo: 'sexta, 31/10/2026, 18:05 (noite)'."""
    t = time.localtime(ts)
    return f"{DAYS[t.tm_wday]}, {time.strftime('%d/%m/%Y, %H:%M', t)} ({part_of_day(t.tm_hour)})"


TASK = """TAREFA DO APLICATIVO (não é mensagem do usuário, não responda como conversa).
Escreva as falas soltas que você vai dizer sozinha no balão nas próximas horas, conforme o que acontece com
você na tela. Reaja ao dia e à hora (madrugada, segunda de manhã, sexta à noite, fim de semana, feriado...).

AGORA: {now}. É {part} de {day}: o que você fala tem que combinar com isso (não diga outra hora ou outro dia).
{school}
CONVERSA RECENTE COM O USUÁRIO (pode fazer referência, sem repetir as frases; é só histórico):
{chat}

SITUAÇÕES (escreva a quantidade pedida de falas diferentes para cada uma, até 100 caracteres cada, com a sua voz:
desbocada, roleplay, sem oferecer ajuda, sem etiqueta de humor; ação curta *assim* de vez em quando).
Palavrão na maioria das falas, gíria, deboche; nada de frase certinha de assistente. Exemplos do tom:
"Puta merda, {part} de {day} e eu aqui presa num desktop." / "Larga, porra, eu fico tonta!" /
"Bowie, sua desgraça, sai de cima do teclado." / "Cê sumiu, caralho? Vou começar a cobrar aluguel."
{cats}

Diga também seu humor agora e de 2 a 4 coisas que você tá com vontade de fazer, SÓ desta lista: {wants}.

Responda SÓ com um JSON válido, sem nada antes ou depois, neste formato:
{{"humor": "...", "vontades": ["...", "..."], "falas": {{"idle": ["...", "..."], "lendo": ["..."]}}}}"""


def parse(raw, wants):
    """Resposta do modelo → (humor, vontades válidas, {categoria: [falas]}). Lixo vira ValueError."""
    t = re.sub(r"```(?:json)?", "", raw or "")
    i, j = t.find("{"), t.rfind("}")
    if i < 0 or j <= i:
        raise ValueError("sem JSON")
    d = json.loads(t[i:j + 1])
    lines = {}
    for cat, items in (d.get("falas") or {}).items():
        if cat not in CATS or not isinstance(items, list):
            continue
        ok = []
        for s in items:
            if isinstance(s, str):
                s = prompts.untag(s).strip().strip('"')
                if 2 <= len(s) <= MAX_LEN and s not in ok:
                    ok.append(s)
        if ok:
            lines[cat] = ok
    if not lines:
        raise ValueError("JSON sem falas")
    w = [a for a in d.get("vontades") or [] if isinstance(a, str) and a in wants][:4]
    mood = d.get("humor") if isinstance(d.get("humor"), str) else ""
    return mood[:40], w, lines


class Mind(QObject):
    updated = Signal()
    _done = Signal(object)

    def __init__(self, provider, persona, conv, store, settings, wants, clock=time.time, path=PATH):
        super().__init__()
        self.provider, self.persona, self.conv, self.store, self.s = provider, persona, conv, store, settings
        self.wants_allowed = list(wants)
        self.now, self.path = clock, path
        self.lines, self.mood, self.wants, self.at = {}, "", [], 0.0
        self.busy = False
        self.last_error = None
        try:
            with open(path, encoding="utf8") as f:
                d = json.load(f)
            self.lines = {k: v for k, v in d.get("lines", {}).items() if k in CATS}
            self.mood, self.wants, self.at = d.get("mood", ""), d.get("wants", []), d.get("at", 0.0)
        except (OSError, ValueError):
            pass
        self.timer = QTimer(self, timeout=self.maybe_refresh)
        self._done.connect(self._finish)

    def start(self):
        self.timer.start(REFRESH * 1000)
        QTimer.singleShot(FIRST * 1000, self.maybe_refresh)

    # --- usado pela fala e pela rotina ---
    def take(self, cat):
        """Uma fala da IA para a situação (cada uma sai uma vez); None = usa as prontas."""
        bag = self.lines.get(cat)
        if not bag:
            return None
        text = bag.pop(0)
        self._save()
        return text

    def boost(self, aid):
        return 3 if aid in self.wants else 1

    # --- pedido à IA ---
    def maybe_refresh(self, after_chat=False):
        gap = AFTER_CHAT if after_chat else REFRESH - 60
        if self.busy or self.now() - self.at < gap or not self.provider.is_available()[0]:
            return False
        try:
            prompt = self.build()
        except OSError:
            return False
        self.busy = True
        threading.Thread(target=self._work, args=(prompt,), daemon=True).start()
        return True

    def build(self):
        chat = prompts.markdown(self.conv.recent(20, 400), 1500) or "(nenhuma ainda)"
        school = ""
        if self.s.get("ai_academic"):
            school = "FACULDADE (Sala Virtual): " + " ".join(texts.answer(self.store, "resumo", self.now())[:2]) + "\n"
        cats = "\n".join(f"- {c} ({n}): {d}" for c, (d, n) in CATS.items())
        t = time.localtime(self.now())
        msg = TASK.format(now=now_text(self.now()), part=part_of_day(t.tm_hour), day=DAYS[t.tm_wday],
                          school=school, chat=chat, cats=cats,
                          wants=", ".join(self.wants_allowed))
        return Prompt(system=self.persona.instructions(), message=msg, max_out=4000, json=True)

    def _work(self, prompt):
        try:
            r = self.provider.send_message(prompt, 90)
            self._done.emit((parse(r.text, self.wants_allowed), None))
        except (AIError, ValueError) as e:
            self._done.emit((None, e))
        except Exception as e:  # nada daqui derruba a Ceci
            self._done.emit((None, e))

    def _finish(self, res):
        data, err = res
        self.busy = False
        self.at = self.now()  # falhou também conta: tenta de novo só no próximo ciclo
        if err is not None:
            self.last_error = str(err)
            return self._save()
        self.mood, self.wants, self.lines = data
        self.last_error = None
        self._save()
        self.updated.emit()

    def _save(self):
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf8") as f:
                json.dump({"at": self.at, "mood": self.mood, "wants": self.wants, "lines": self.lines}, f,
                          ensure_ascii=False, indent=0)
            os.replace(tmp, self.path)
        except OSError:
            pass
