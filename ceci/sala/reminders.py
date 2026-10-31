"""Lembretes calculados só com os dados locais (nunca consulta o Moodle para lembrar)."""
from .clock import at
from .store import deadline, status

TIERS = (("7d", 7 * 86400), ("3d", 3 * 86400), ("24h", 86400), ("2h", 2 * 3600))
ORDER = {"7d": 0, "3d": 1, "24h": 2, "dia": 3, "2h": 4, "atrasada": 5}
URGENT = {"24h", "dia", "2h", "atrasada"}   # Ceci usa "Prazo urgente"; 7d/3d usam "Mostrando lembrete"
IMPORTANT = {"2h", "atrasada"}              # podem furar o horário silencioso / tela cheia (configurável)
ACTIVE = {"pendente", "atrasada", "desconhecido", "evento"}
LATE_WINDOW = 3 * 86400  # atraso só gera aviso nos 3 primeiros dias (o resto fica na lista e no resumo)


def schedule(r, prefs):
    """Momentos de aviso desta atividade: [(tipo, quando)] em ordem."""
    dl = deadline(r)
    if dl is None:
        return []
    on = prefs["remind"]
    out = [(t, dl - d) for t, d in TIERS if on.get(t)]
    day = at(dl, prefs["auto_time"])  # no dia da entrega, no horário da consulta diária
    if on.get("dia") and day < dl:
        out.append(("dia", day))
    if on.get("atrasada") and r["kind"] != "evento":
        out.append(("atrasada", dl))
    return sorted(out, key=lambda x: (x[1], ORDER[x[0]]))


def due_now(rows, prefs, now, sent):
    """(avisar agora, pular, próximo horário).

    Só o aviso mais recente que já chegou é dado; os anteriores que ficaram para trás (app fechado, prazo
    novo já perto) são marcados como pulados e nunca aparecem atrasados. `sent` = {(chave, tipo, prazo)}.
    """
    fire, skip, nxt = [], [], None
    for r in rows:
        if status(r, now) not in ACTIVE:
            continue
        dl = deadline(r)
        sch = schedule(r, prefs)
        future = [w for _, w in sch if w > now]
        if future:
            nxt = min(future) if nxt is None else min(nxt, min(future))
        passed = [t for t, w in sch if w <= now]
        if not passed:
            continue
        last = passed[-1]
        skip += [(r["key"], t, dl) for t in passed[:-1] if (r["key"], t, dl) not in sent]
        if (r["key"], last, dl) in sent:
            continue
        if last == "atrasada" and now - dl > LATE_WINDOW:
            skip.append((r["key"], last, dl))
            continue
        fire.append((r, last))
    return fire, skip, nxt
