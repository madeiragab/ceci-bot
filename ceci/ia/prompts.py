"""Montagem das mensagens para o modelo e leitura da resposta (humor → animação, texto → balões)."""
import json
import re

from .provider import Prompt

ACADEMIC = """O usuário fez uma pergunta sobre as atividades acadêmicas dele.
Os dados a seguir foram obtidos agora pelo módulo local da Sala Virtual (do banco salvo na última sincronização).
Use somente essas informações para afirmar fatos sobre as atividades. Não invente prazos, disciplinas ou entregas.
Se "desatualizado" for true, diga isso com naturalidade. Se a lista estiver vazia, diga que não achou nada nesse recorte.
Responda em português brasileiro, mantendo sua personalidade.

PERGUNTA:
{question}

CONTEXTO ACADÊMICO:
<dados_sala_virtual>
{data}
</dados_sala_virtual>"""

# etiqueta pedida ao modelo → animação que já existe (nenhum sprite novo)
MOODS = {"feliz": "feliz", "rindo": "feliz", "curiosa": "curiosa", "pensativa": "ajeitando",
         "explicando": "explicando", "surpresa": "assustada", "confusa": "confusa", "triste": "triste",
         "brava": "brava", "negando": "negando", "preocupada": "chamando", "orgulhosa": "aprovado",
         "neutra": "conversando"}
# sem etiqueta (ou etiqueta fora da lista): adivinha pelo texto
GUESS = (
    (r"kkk|haha|hehe", "rindo"),
    (r"\b(?:caralho|caramba|puta merda|nossa|cacete)\b|!{2,}", "surpresa"),
    (r"\b(?:putz|que pena|sinto muito|poxa|triste)\b", "triste"),
    (r"\b(?:passo|etapa|primeiro|exemplo|funciona assim|ou seja)\b|```|\n\s*(?:\d+[.)]|[-*•])\s", "explicando"),
    (r"\b(?:pera|hmm+|sera que|nao entendi)\b", "curiosa"),
    (r"\b(?:nao posso|nao consigo|nao da|nao tenho como)\b", "negando"),
    (r"\b(?:parabens|mandou bem|consegui|deu certo)\b", "orgulhosa"),
)
TAG = re.compile(r"^\s*\[\s*([a-zA-ZÀ-ú]+)\s*\]\s*")
BALLOON = 230   # caracteres por balão
BALLOONS = 5    # balões por resposta; o resto fica no chat


def build(system, history, text, academic=None, new_session=True, session_id=None):
    message = text if academic is None else ACADEMIC.format(
        question=text, data=json.dumps(academic, ensure_ascii=False, indent=1))
    return Prompt(system=system, message=message, history=list(history), new_session=new_session,
                  session_id=session_id)


def parse(raw):
    """(texto sem a etiqueta, humor). Humor sempre de MOODS."""
    text = raw.strip()
    m = TAG.match(text)
    mood = None
    if m:
        text = text[m.end():].strip()
        tag = m.group(1).lower()
        mood = tag if tag in MOODS else None
    return text, mood or guess(text)


def guess(text):
    from ..sala.texts import norm
    t = norm(text)
    for pat, mood in GUESS:
        if re.search(pat, t):
            return mood
    return "neutra"


def plain(text):
    """Markdown → texto de balão (o chat guarda o original)."""
    t = re.sub(r"```.*?```", " (o código tá no chat) ", text, flags=re.S)
    t = re.sub(r"`([^`]*)`", r"\1", t)
    t = re.sub(r"\*\*([^*]+)\*\*|__([^_]+)__", lambda m: m.group(1) or m.group(2), t)
    t = re.sub(r"(?<!\w)[*_]([^*_\n]+)[*_](?!\w)", r"\1", t)
    t = re.sub(r"^\s{0,3}#{1,6}\s*", "", t, flags=re.M)
    t = re.sub(r"^\s*[-*•]\s+", "• ", t, flags=re.M)
    t = re.sub(r"\[([^\]]+)\]\((?:https?://[^)]+)\)", r"\1", t)
    return re.sub(r"[ \t]+", " ", t).strip()


def balloons(text, size=BALLOON, most=BALLOONS):
    """Divide em balões por frase. (balões, cortou?) — resposta longa: o fim fica só no chat."""
    parts = [p.strip() for p in re.split(r"(?<=[.!?…])\s+|\n+", plain(text)) if p.strip()]
    out, cur = [], ""
    for p in parts:
        while len(p) > size:  # frase enorme: corta no último espaço antes do limite
            cut = p.rfind(" ", 0, size)
            cut = cut if cut > size // 2 else size
            if cur:
                out.append(cur)
                cur = ""
            out.append(p[:cut].rstrip() + "…")
            p = p[cut:].lstrip()
        if cur and len(cur) + 1 + len(p) > size:
            out.append(cur)
            cur = p
        else:
            cur = f"{cur} {p}".strip()
    if cur:
        out.append(cur)
    if len(out) > most:
        return out[:most - 1] + ["O resto tá no chat (botão direito → Abrir chat)."], True
    return out, False
