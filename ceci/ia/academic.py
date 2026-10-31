"""Recorte dos dados da Sala Virtual para uma pergunta: só o que ela precisa, nunca o banco inteiro.

Fonte: o SQLite da Sala Virtual (ceci/sala/store.py), sem consultar o Moodle de novo.
"""
import re

from ..sala.clock import local, when
from ..sala.store import KIND_LABEL, STATUS_LABEL, deadline, status
from ..sala.texts import freshness, name, norm, spoken_course

MAX_ITEMS = 15
DESC_CHARS = 1500  # descrição da tarefa: só quando pedem ajuda com uma atividade específica


def intent(t):
    """Que recorte a pergunta pede (t já normalizado). Também serve para a resposta local sem IA."""
    if "atrasad" in t:
        return "atrasadas"
    if "amanha" in t:
        return "amanha"
    if "hoje" in t:
        return "hoje"
    if re.search(r"semana|proximos dias", t):
        return "semana"
    if re.search(r"cronograma|organiz|planej", t):
        return "cronograma"
    if re.search(r"primeir|proxim|mais cedo|mais perto|qual vence", t):
        return "prazo"
    return "atividades"


def explain(t):
    return bool(re.search(r"resolv|explica|como (?:faz|fazer|comeco)|me ajuda (?:com|a fazer)|entender", t))


def iso(ts):
    return local(ts).isoformat(timespec="minutes") if ts else None


def course_names(store):
    """Nomes das disciplinas como se fala, sem acento (o roteador reconhece "pesquisa operacional")."""
    return sorted({norm(spoken_course(dict(r))) for r in store.rows()} - {""}, key=len, reverse=True)


def build(store, text, now, prev_keys=(), follow=False):
    """(contexto para o modelo, chaves das atividades usadas). `text` já normalizado."""
    rows = [dict(r) for r in store.rows()]
    st = {r["key"]: status(r, now) for r in rows}
    todo = [r for r in rows if st[r["key"]] in ("pendente", "desconhecido", "atrasada")]
    start = local(now).replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    kind = intent(text)
    if follow and prev_keys:  # "e qual delas vence primeiro?": o mesmo conjunto da resposta anterior
        by_key = {r["key"]: r for r in rows}
        pick = [by_key[k] for k in prev_keys if k in by_key]
    else:
        up = sorted((r for r in todo if st[r["key"]] != "atrasada" and deadline(r)), key=deadline)
        late = sorted((r for r in todo if st[r["key"]] == "atrasada"), key=deadline, reverse=True)
        window = {"hoje": (now, start + 86400), "amanha": (start + 86400, start + 2 * 86400),
                  "semana": (now, start + 8 * 86400), "cronograma": (now, start + 15 * 86400)}.get(kind)
        if kind == "atrasadas":
            pick = late
        elif window:
            pick = [r for r in up if window[0] <= deadline(r) < window[1]]
            if kind == "cronograma":
                pick += late[:5]
        else:
            pick = up + late
        mentioned = [r for r in pick if norm(spoken_course(r)) and norm(spoken_course(r)) in text]
        if not mentioned:  # disciplina citada que não está no recorte: procura em tudo que está a fazer
            mentioned = [r for r in todo if norm(spoken_course(r)) and norm(spoken_course(r)) in text]
        pick = mentioned or pick
        named = [r for r in todo if len(norm(r["name"])) > 6 and norm(r["name"]) in text]
        pick = named or pick
    pick = pick[:MAX_ITEMS]
    with_desc = explain(text) and len(pick) <= 3
    ok, last = store.last_success(), store.last_sync()
    fresh, stale = freshness(store, now)
    ctx = {
        "modulo": "sala_virtual",
        "agora": iso(now),
        "ultima_sincronizacao": iso(ok["finished"]) if ok else None,
        "sincronizacao_completa": bool(ok and ok["result"] == "ok"),
        "desatualizado": bool(stale),
        "situacao_dos_dados": fresh,
        "filtro": "seguimento da pergunta anterior" if follow and prev_keys else kind,
        "total_a_fazer": sum(1 for r in todo if st[r["key"]] != "atrasada"),
        "total_atrasadas": sum(1 for r in todo if st[r["key"]] == "atrasada"),
        "atividades": [item(r, st[r["key"]], now, with_desc) for r in pick],
    }
    if not last:
        ctx["aviso"] = "A Sala Virtual ainda não foi consultada: não há dados de atividades."
    return ctx, [r["key"] for r in pick]


def item(r, st, now, with_desc=False):
    dl = deadline(r)
    it = {"disciplina": spoken_course(r), "titulo": name(r, 120), "tipo": KIND_LABEL.get(r["kind"], "Atividade"),
          "prazo": iso(dl), "prazo_falado": when(dl, now) if dl else "sem prazo definido",
          "status": STATUS_LABEL.get(st, st)}
    if dl and now <= dl < now + 86400 and st != "atrasada":
        it["urgente"] = True  # vence em menos de 24 h
    if r["sub"] == "rascunho":
        it["rascunho_salvo_nao_enviado"] = True
    if r["cutoff"] and r["cutoff"] > now and st == "atrasada":
        it["aceita_atrasada_ate"] = iso(r["cutoff"])
    if with_desc and r["summary"]:
        it["descricao"] = r["summary"][:DESC_CHARS]
    return it
