"""Datas no fuso America/Sao_Paulo e textos de prazo ("amanhã às 23:59", "faltam 20 h")."""
from datetime import datetime, timedelta, timezone

try:
    from zoneinfo import ZoneInfo
    TZ = ZoneInfo("America/Sao_Paulo")
except Exception:  # sem base de fusos: o Brasil não tem horário de verão desde 2019
    TZ = timezone(timedelta(hours=-3), "America/Sao_Paulo")

WEEKDAYS = ("seg", "ter", "qua", "qui", "sex", "sáb", "dom")


def local(ts):
    return datetime.fromtimestamp(ts, TZ)


def today(ts):
    return local(ts).date().isoformat()


def at(ts, hhmm, days=0):
    """Timestamp do horário hh:mm no dia de `ts` (+ days), no fuso de São Paulo."""
    d = local(ts).date() + timedelta(days=days)
    h, m = (int(x) for x in hhmm.split(":"))
    return datetime(d.year, d.month, d.day, h, m, tzinfo=TZ).timestamp()


def in_window(ts, start, end):
    """ts está entre start e end (hh:mm)? Aceita janelas que passam da meia-noite (22:00–07:00)."""
    t = local(ts).strftime("%H:%M")
    return start <= t < end if start <= end else t >= start or t < end


def stamp(ts):
    return local(ts).strftime("%d/%m %H:%M") if ts else "nunca"


def when(ts, now):
    d, n = local(ts), local(now)
    days = (d.date() - n.date()).days
    hm = d.strftime("%H:%M")
    if days == 0:
        return f"hoje às {hm}"
    if days == 1:
        return f"amanhã às {hm}"
    if days == -1:
        return f"ontem às {hm}"
    if 1 < days < 7:
        return f"{WEEKDAYS[d.weekday()]} ({d:%d/%m}) às {hm}"
    return f"{d:%d/%m}" + (f"/{d:%Y}" if d.year != n.year else "") + f" às {hm}"


def left(ts, now):
    s = ts - now
    a = abs(s)
    if a < 3600:
        q = f"{max(1, int(a // 60))} min"
    elif a < 2 * 86400:
        q = f"{int(a // 3600)} h"
    else:
        q = f"{int(a // 86400)} dias"
    return f"faltam {q}" if s >= 0 else f"venceu há {q}"
