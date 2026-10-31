"""Textos montados com os dados locais (sem IA): linha de cada atividade, falas de aviso e o Resumo da faculdade."""
import html

from .clock import local, stamp, when, left
from .store import DEADLINE_LABEL, KIND_LABEL, STATUS_LABEL, deadline, deadline_field, status

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
    c, n = course(r), r["name"]
    if tier == "entregue":
        return f"{c}: {n} — o Moodle confirmou a entrega."
    if dl is None:
        return f"{c}: {n} (sem prazo definido)."
    if tier == "prazo_alterado":
        return f"Prazo novo em {c}: {n} — agora {verb} {when(dl, now)}."
    if tier in ("24h", "dia", "2h") and dl > now:
        return f"Criatura, tem atividade de {c} vencendo {when(dl, now)}. Olha isso aqui!"
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


def summary_html(store, now):
    rows = [dict(r) for r in store.rows()]
    by_key = {r["key"]: r for r in rows}
    st = {r["key"]: status(r, now) for r in rows}
    start = local(now).replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    todo = [r for r in rows if st[r["key"]] in ("pendente", "desconhecido", "evento") and deadline(r)]
    today = sorted([r for r in todo if start <= deadline(r) < start + 86400], key=deadline)
    week = sorted([r for r in todo if start + 86400 <= deadline(r) < start + 8 * 86400], key=deadline)
    late = sorted([r for r in rows if st[r["key"]] == "atrasada"], key=deadline, reverse=True)
    ok = store.last_success()
    new = [by_key[c["key"]] for c in (store.changes(sync_id=ok["id"], kinds=["nova"]) if ok else []) if c["key"] in by_key]
    moved = [(c, by_key[c["key"]]) for c in store.changes(since=now - 7 * 86400, kinds=["prazo"]) if c["key"] in by_key]

    def item(r, extra=""):
        url = html.escape(r["url"] or "", quote=True)
        name = html.escape(r["name"])
        link = f'<a href="{url}">{name}</a>' if url else name
        return (f"<li>{link}<br><span class='m'>{html.escape(course(r))} · {html.escape(deadline_text(r, now))}"
                f" · {STATUS_LABEL[st[r['key']]]}{extra}</span></li>")

    def section(title, items, empty):
        body = "".join(items) if items else f"<li class='m'>{empty}</li>"
        return f"<h3>{title}</h3><ul>{body}</ul>"

    fresh, warn = freshness(store, now)
    out = [f"<p class='{'w' if warn else 'm'}'>{html.escape(fresh)}</p>",
           section("Hoje", [item(r) for r in today], "Nada vence hoje."),
           section("Esta semana", [item(r) for r in week], "Nada para os próximos 7 dias."),
           section("Atrasadas", [item(r) for r in late], "Nenhuma atividade atrasada."),
           section("Novidades da última sincronização", [item(r) for r in new], "Nenhuma atividade nova."),
           section("Alterações de prazo (últimos 7 dias)",
                   [item(r, f" · antes: {when(float(c['before']), now) if c['before'] not in (None, 'None') else 'sem prazo'}")
                    for c, r in moved], "Nenhum prazo mudou.")]
    return "".join(out)
