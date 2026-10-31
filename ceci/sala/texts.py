"""Textos montados com os dados locais (sem IA): falas de aviso e as respostas sobre as atividades."""
import re
import unicodedata


from .clock import local, stamp, when, left
from .store import DEADLINE_LABEL, KIND_LABEL, deadline, deadline_field, status

TODO = ("atrasada", "pendente", "desconhecido", "sem_prazo", "evento")
SORT = {"atrasada": 0, "pendente": 1, "desconhecido": 1, "evento": 1, "sem_prazo": 2, "manual": 3, "entregue": 4,
        "concluida": 4, "indisponivel": 5, "passado": 6}


def course(r):
    name = r.get("course_name") or r.get("course_short") or "Sala Virtual"
    return name if len(name) <= 48 else name[:47].rstrip() + "…"


def deadline_text(r, now):
    dl, f = deadline(r), deadline_field(r)
    if dl is None:
        return "Sem prazo definido"
    return f"{DEADLINE_LABEL[f]}: {when(dl, now)} · {left(dl, now)}"


def info(r, now):
    """Linha secundária da atividade: tipo, prazo e o que o Moodle confirmou."""
    bits = [KIND_LABEL.get(r["kind"], "Atividade"), deadline_text(r, now)]
    st = status(r, now)
    if r["sub"] == "rascunho" and st in ("pendente", "atrasada"):
        bits.append("rascunho salvo, ainda NÃO enviado")
    if st == "atrasada" and r["cutoff"] and r["cutoff"] > now:
        bits.append(f"aceita atrasada até {when(r['cutoff'], now)}")
    return " · ".join(bits)


def sort_key(r, now):
    dl = deadline(r)
    st = status(r, now)
    return SORT.get(st, 9), (dl if dl is not None else 9e12) * (-1 if st in ("passado", "entregue") else 1)


def speech_line(item, now):
    """O que a Ceci diz depois da frase do banco, sempre com a disciplina, a atividade e o prazo de verdade."""
    r, tier = item["row"], item["tier"]
    dl, f = deadline(r), deadline_field(r)
    verb = {"due": "entrega", "close": "fecha", "expected": "conclusão esperada"}.get(f, "prazo")
    c, n = spoken_course(r), r["name"]
    if tier == "entregue":
        return f"{c}: {n} — o Moodle confirmou a entrega."
    if dl is None:
        return f"{c}: {n} (sem prazo definido)."
    if tier == "prazo_alterado":
        return f"Prazo novo em {c}: {n} — agora {verb} {when(dl, now)}."
    if tier in ("24h", "dia", "2h") and dl > now:
        return f"Criatura, tem atividade de {c} vencendo {when(dl, now)}: {n}."
    if tier == "atrasada":
        late = f" Ainda aceita até {when(r['cutoff'], now)}." if r["cutoff"] and r["cutoff"] > now else ""
        return f"{c}: {n} venceu {when(dl, now)} e o Moodle não confirmou a entrega.{late}"
    return f"{c}: {n} — {verb} {when(dl, now)} ({left(dl, now)})."


def speech_category(item, now):
    tier, r = item["tier"], item["row"]
    if tier == "nova":
        return "sv_nova"
    if tier == "entregue":
        return "sv_entregue"
    if tier in ("prazo_alterado", "7d", "3d"):
        return "sv_prazo"
    if tier == "atrasada":
        return "sv_atrasada"
    dl = deadline(r)
    return "sv_hoje" if dl and local(dl).date() == local(now).date() and dl > now else "sv_urgente"


def toast(items, now):
    """(título, texto) da notificação do Windows."""
    if len(items) == 1:
        i = items[0]
        r = i["row"]
        title = {"nova": "Atividade nova", "entregue": "Entrega confirmada", "prazo_alterado": "Prazo alterado",
                 "atrasada": "Atividade atrasada"}.get(i["tier"], "Prazo chegando")
        return f"{title} · {course(r)}", f"{r['name']}\n{deadline_text(r, now)}\nClique para abrir no Moodle."
    kinds = {}
    for i in items:
        k = {"nova": "nova(s)", "entregue": "entrega(s) confirmada(s)", "prazo_alterado": "prazo(s) alterado(s)"}.get(
            i["tier"], "prazo(s) chegando")
        kinds[k] = kinds.get(k, 0) + 1
    return (f"Sala Virtual · {len(items)} avisos", ", ".join(f"{v} {k}" for k, v in kinds.items())
            + "\nClique para ver as atividades.")


def freshness(store, now):
    """Quando os dados foram atualizados — e se a última consulta falhou depois disso."""
    ok, last = store.last_success(), store.last_sync()
    if not last:
        return "Ainda não houve nenhuma sincronização.", True
    if ok is None:
        return f"A última consulta ({stamp(last['started'])}) falhou: {last['message']}", True
    txt = f"Dados de {stamp(ok['finished'])}" + (" (consulta parcial)" if ok["result"] == "parcial" else "")
    warn = ok["result"] == "parcial" or now - ok["finished"] > 26 * 3600
    if last["id"] != ok["id"]:
        txt += f". A consulta de {stamp(last['started'])} falhou: {last['message']}"
        warn = True
    elif now - ok["finished"] > 26 * 3600:
        txt += ". Pode ter coisa nova desde então."
    return txt, warn


def name(r, size=70):
    n = r["name"]
    return n if len(n) <= size else n[:size - 1].rstrip() + "…"


def spoken_course(r):
    """Disciplina como se fala: "34 - Teoria da Computação - COMP6_MUZ" → "Teoria da Computação"."""
    c = re.sub(r"^\d+\s*-\s*", "", r.get("course_name") or r.get("course_short") or "Sala Virtual")
    return re.sub(r"\s*-\s*[A-Z0-9_]+$", "", c) or course(r)


def line(r, now):
    """Uma atividade numa fala: nome, disciplina e prazo."""
    dl, c = deadline(r), spoken_course(r)
    if dl is None:
        return f"{name(r)} ({c}), sem prazo definido."
    if dl < now:
        return f"{name(r)} ({c}) venceu {when(dl, now)}."
    return f"{name(r)} ({c}): {when(dl, now)}, {left(dl, now)}."


def _groups(store, now):
    rows = [dict(r) for r in store.rows()]
    st = {r["key"]: status(r, now) for r in rows}
    up = sorted((r for r in rows if st[r["key"]] in ("pendente", "desconhecido") and deadline(r)), key=deadline)
    late = sorted((r for r in rows if st[r["key"]] == "atrasada"), key=deadline, reverse=True)
    return rows, up, late


def answer(store, what, now, limit=5):
    """O que a Ceci fala quando você pergunta (menu ou caixinha). Só com os dados da última consulta."""
    if not store.last_sync():
        return ["Ainda não conferi a Sala Virtual. Me conecta nas Configurações ou digita \"conferir\"."]
    rows, up, late = _groups(store, now)
    start = local(now).replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    say = []
    if what == "atividades":
        if not up and not late:
            say.append("Nada pendente na Sala Virtual. Milagre!")
        else:
            say.append(f"Tem {len(up)} pra fazer" + (f" e {len(late)} atrasada(s)." if late else "."))
            say += [line(r, now) for r in up[:limit]]
            say += ["Atrasadas: " + line(r, now) if i == 0 else line(r, now) for i, r in enumerate(late[:3])]
            rest = max(0, len(up) - limit) + max(0, len(late) - 3)
            if rest:
                say.append(f"E mais {rest}.")
    elif what == "prazo":
        nxt = [r for r in up if deadline(r) >= now]
        say.append("A próxima é " + line(nxt[0], now) if nxt else "Nenhum prazo pela frente.")
    elif what in ("hoje", "amanha", "semana"):
        a, b, label = {"hoje": (now, start + 86400, "hoje"), "amanha": (start + 86400, start + 2 * 86400, "amanhã"),
                       "semana": (now, start + 8 * 86400, "nos próximos 7 dias")}[what]
        got = [r for r in up if a <= deadline(r) < b]
        say.append(f"{len(got)} vencendo {label}." if got else f"Nada vencendo {label}.")
        say += [line(r, now) for r in got[:limit]]
        if len(got) > limit:
            say.append(f"E mais {len(got) - limit}.")
    elif what == "atrasadas":
        say.append(f"{len(late)} atrasada(s)." if late else "Nenhuma atividade atrasada.")
        say += [line(r, now) for r in late[:limit]]
        if len(late) > limit:
            say.append(f"E mais {len(late) - limit}.")
    elif what == "resumo":
        today = [r for r in up if now <= deadline(r) < start + 86400]
        week = [r for r in up if now <= deadline(r) < start + 8 * 86400]
        ok = store.last_success()
        new = store.changes(sync_id=ok["id"], kinds=["nova"]) if ok else []
        say.append(f"Hoje vence {len(today)}, na semana {len(week)}, atrasadas {len(late)}"
                   + (f" e {len(new)} nova(s) na última consulta." if new else "."))
        if week:
            say.append("A próxima é " + line(week[0], now))
    fresh, warn = freshness(store, now)
    if warn:
        say.append(fresh)
    return say


def norm(text):
    """Minúsculas, sem acento e sem espaço repetido (o que você digita x o nome no Moodle)."""
    t = unicodedata.normalize("NFD", text.casefold())
    return " ".join("".join(c for c in t if not unicodedata.combining(c)).split())


def find(store, text, now, done=False):
    """Atividades a fazer (done=True: as marcadas por você) cujo nome tem o texto digitado."""
    t = norm(text)
    want = ("manual",) if done else ("pendente", "desconhecido", "atrasada")
    return [dict(r) for r in store.rows() if t and t in norm(r["name"]) and status(r, now) in want]
