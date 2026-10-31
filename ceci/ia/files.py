"""Arquivos .txt/.md que o usuário entrega para a Ceci ler.

Arquivo que cabe (até LIMIT caracteres) vai inteiro. Arquivo maior (um transcript de 4 MB, por exemplo) é
dividido em trechos e, a cada pergunta, vão só os trechos que mais falam do que foi perguntado, na ordem
em que aparecem no arquivo. Sem pergunta específica ("lê e me diz o que achou"): o começo e amostras
espalhadas. O texto inteiro fica só na memória; o histórico guarda nome, caminho e tamanho.
"""
import math
import os
import re
from collections import Counter

from ..sala.texts import norm

TYPES = (".txt", ".md", ".markdown")
MAX_BYTES = 50_000_000
LIMIT = 100_000   # caracteres que vão para a IA por pergunta (~30 mil tokens)
CHUNK = 3000      # tamanho de cada trecho
STOP = set("""a o e é de da do das dos que em no na nos nas um uma uns umas pra para por com sem se me te
lhe eu tu ele ela nós vós eles elas cê voce você isso esse essa este esta aquilo aquele aquela qual quais
quando onde como porque pq mais menos muito muita ja já não nao sim mas ou foi era ser ter tem tinha
arquivo texto lê le ler fala falar diz dizer sobre achou acha coisa coisas aí ai ali aqui lá la tá ta""".split())


def read(path):
    """Texto do arquivo (UTF-8, ou o padrão do Windows). OSError/ValueError com o motivo."""
    if os.path.splitext(path)[1].lower() not in TYPES:
        raise ValueError("tipo")
    if os.path.getsize(path) > MAX_BYTES:
        raise ValueError("grande")
    with open(path, "rb") as fh:
        raw = fh.read()
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return raw.decode(enc).replace("\r\n", "\n").strip()
        except UnicodeDecodeError:
            continue


def chunks(text):
    out, start = [], 0
    while start < len(text):
        end = min(len(text), start + CHUNK)
        if end < len(text):  # corta numa quebra de linha perto do fim
            nl = text.rfind("\n", start + CHUNK // 2, end)
            end = nl + 1 if nl > 0 else end
        out.append(text[start:end])
        start = end
    return out


def terms(question):
    return [w for w in re.findall(r"\w+", norm(question)) if len(w) >= 3 and w not in STOP]


def excerpt(text, question, limit=LIMIT, generic=True):
    """(texto que vai para a IA, descrição do recorte ou "" quando foi inteiro).
    generic=False (perguntas depois da primeira): pergunta que não fala de nada do arquivo → ("", "")."""
    q = terms(question)
    if not generic and not any(t in norm(text) for t in q):
        return "", ""
    if len(text) <= limit:
        return text, ""
    parts = chunks(text)
    n = len(parts)
    budget = max(1, limit // CHUNK)
    low = [norm(p) for p in parts] if q else []
    df = {t: sum(1 for p in low if t in p) for t in set(q)}
    scored = []
    for i, p in enumerate(low):
        c = Counter(re.findall(r"\w+", p))
        s = sum((c[t] or (0.5 if t in p else 0)) * math.log(1 + n / (1 + df[t])) for t in set(q))
        scored.append((s, i))
    best = [i for s, i in sorted(scored, reverse=True) if s > 0][:budget]
    if best:
        how = f"os {len(best)} trechos que mais falam de: {', '.join(dict.fromkeys(q))}"
        if len(best) < budget:  # sobrou espaço: completa com o começo
            best += [i for i in range(n) if i not in best][:budget - len(best)]
    else:  # pergunta genérica: começo + amostras espalhadas
        head = budget // 2
        step = max(1, (n - head) // max(1, budget - head))
        best = list(range(min(head, n))) + list(range(head, n, step))[:budget - head]
        how = "o começo e amostras espalhadas"
    pieces = [f"[trecho {i + 1} de {n}]\n{parts[i]}" for i in sorted(set(best))]
    return "\n\n".join(pieces), how
