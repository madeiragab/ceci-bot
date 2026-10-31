"""Banco local (SQLite) da Sala Virtual: disciplinas, atividades, histórico, sincronizações, avisos e preferências.

Tudo aqui funciona offline com o que a última sincronização trouxe. Nada é apagado só porque sumiu de uma
consulta: vira "indisponível", com a data em que sumiu.
"""
import json
import os
import sqlite3
import time
from contextlib import contextmanager

from ..settings import CONFIG_DIR
from .clock import today
from .moodle import DEFAULT_URL

PATH = os.path.join(CONFIG_DIR, "sala_virtual.db")
DATES = ("open", "due", "close", "cutoff", "expected")

SCHEMA = """
CREATE TABLE IF NOT EXISTS courses(id INTEGER PRIMARY KEY, name TEXT, short TEXT, url TEXT, past INTEGER DEFAULT 0,
    first_seen REAL, last_seen REAL, gone_since REAL);
CREATE TABLE IF NOT EXISTS activities(key TEXT PRIMARY KEY, cmid INTEGER, course INTEGER, name TEXT, mod TEXT,
    kind TEXT, summary TEXT, open REAL, due REAL, close REAL, cutoff REAL, expected REAL, sub TEXT,
    completion INTEGER, manual INTEGER DEFAULT 0, manual_at REAL, url TEXT, sources TEXT,
    state TEXT DEFAULT 'ativa', first_seen REAL, last_seen REAL, checked_at REAL, gone_since REAL, sync_id INTEGER);
CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY, key TEXT, field TEXT);
CREATE TABLE IF NOT EXISTS changes(id INTEGER PRIMARY KEY AUTOINCREMENT, at REAL, sync_id INTEGER, key TEXT,
    kind TEXT, before TEXT, after TEXT);
CREATE TABLE IF NOT EXISTS syncs(id INTEGER PRIMARY KEY AUTOINCREMENT, started REAL, finished REAL, trigger TEXT,
    day TEXT, result TEXT, kind TEXT, courses INTEGER, courses_ok INTEGER, activities INTEGER, message TEXT);
CREATE TABLE IF NOT EXISTS notifications(id INTEGER PRIMARY KEY AUTOINCREMENT, at REAL, key TEXT, tier TEXT,
    due REAL, how TEXT, UNIQUE(key, tier, due));
CREATE TABLE IF NOT EXISTS prefs(key TEXT PRIMARY KEY, value TEXT);
"""

PREFS = {
    "url": DEFAULT_URL,
    "auto_time": "08:00",  # a única consulta automática do dia (America/Sao_Paulo)
    "remind": {"7d": True, "3d": True, "24h": True, "2h": True, "dia": True, "atrasada": True},
    "quiet": True, "quiet_start": "22:00", "quiet_end": "07:00",
    "urgent_quiet": False,      # alertas importantes (2 h e atraso) furam o horário silencioso?
    "urgent_fullscreen": True,  # ... e aparecem (só a notificação do Windows) em tela cheia?
    "toast": True,              # notificação do Windows
    "ceci": True,               # a Ceci avisa com animação e balão
}

STATUS_LABEL = {
    "pendente": "Pendente", "entregue": "Entrega confirmada pelo Moodle",
    "concluida": "Concluída (critério do Moodle)", "atrasada": "Atrasada", "sem_prazo": "Sem prazo definido",
    "desconhecido": "Status desconhecido", "manual": "Marcada por você (o Moodle não confirmou)",
    "indisponivel": "Indisponível na Sala Virtual", "evento": "Evento do calendário", "passado": "Evento passado",
}
KIND_LABEL = {"envio": "Tarefa (envio)", "questionario": "Questionário", "forum": "Fórum", "evento": "Evento",
              "outro": "Atividade"}
DEADLINE_LABEL = {"due": "Entrega", "close": "Fecha", "expected": "Conclusão esperada"}


def deadline(r):
    return r["due"] or r["close"] or r["expected"]


def deadline_field(r):
    return next((f for f in ("due", "close", "expected") if r[f]), None)


def status(r, now):
    if r["sub"] == "enviado":
        return "entregue"
    if r["completion"] in (1, 2, 3) and r["mod"] not in ("assign", "quiz"):
        return "concluida"  # tarefa/questionário só valem pelo envio (conclusão pode ser só "visualizou")
    if r["manual"]:
        return "manual"
    if r["state"] != "ativa":
        return "indisponivel"
    dl = deadline(r)
    if dl is None:
        return "sem_prazo"
    if r["kind"] == "evento":
        return "evento" if dl >= now else "passado"
    if dl < now:
        return "atrasada"
    if r["sub"] in ("nenhum", "rascunho", "reaberto"):
        return "pendente"
    return "desconhecido"


class Store:
    def __init__(self, path=PATH):
        self.path = path
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with self.db() as con:
            con.executescript(SCHEMA)

    @contextmanager
    def db(self):
        con = sqlite3.connect(self.path, timeout=15)
        con.row_factory = sqlite3.Row
        try:
            with con:
                yield con
        finally:
            con.close()

    # --- preferências ---
    def prefs(self):
        with self.db() as con:
            saved = {r["key"]: json.loads(r["value"]) for r in con.execute("SELECT key, value FROM prefs")}
        p = {**PREFS, **{k: v for k, v in saved.items() if k in PREFS}}
        p["remind"] = {**PREFS["remind"], **p["remind"]}
        return p

    def set_prefs(self, **kw):
        with self.db() as con:
            con.executemany("INSERT OR REPLACE INTO prefs(key, value) VALUES (?, ?)",
                            [(k, json.dumps(v)) for k, v in kw.items() if k in PREFS])

    # --- sincronizações ---
    def begin_sync(self, trigger, now):
        with self.db() as con:
            return con.execute("INSERT INTO syncs(started, trigger, day, result) VALUES (?, ?, ?, 'andamento')",
                               (now, trigger, today(now))).lastrowid

    def finish_sync(self, sid, result, kind, message, now, courses=0, courses_ok=0, activities=0):
        with self.db() as con:
            con.execute("UPDATE syncs SET finished=?, result=?, kind=?, message=?, courses=?, courses_ok=?, "
                        "activities=? WHERE id=?", (now, result, kind, message, courses, courses_ok, activities, sid))

    def mark_interrupted(self):
        """Consulta que não terminou (app fechado no meio): fica registrada como interrompida."""
        with self.db() as con:
            con.execute("UPDATE syncs SET result='interrompida', kind='interrompida' WHERE finished IS NULL")

    def last_auto_day(self):
        with self.db() as con:
            r = con.execute("SELECT day FROM syncs WHERE trigger='auto' ORDER BY id DESC LIMIT 1").fetchone()
        return r["day"] if r else None

    def last_sync(self):
        with self.db() as con:
            return con.execute("SELECT * FROM syncs WHERE finished IS NOT NULL ORDER BY id DESC LIMIT 1").fetchone()

    def last_success(self, full=False):
        q = "result='ok'" if full else "result IN ('ok', 'parcial')"
        with self.db() as con:
            return con.execute(f"SELECT * FROM syncs WHERE {q} ORDER BY id DESC LIMIT 1").fetchone()

    # --- atividades ---
    def known(self):
        with self.db() as con:
            return {r["key"]: r for r in con.execute("SELECT * FROM activities")}

    def rows(self):
        with self.db() as con:
            return con.execute("SELECT a.*, c.name AS course_name, c.short AS course_short FROM activities a "
                               "LEFT JOIN courses c ON c.id = a.course").fetchall()

    def courses(self):
        with self.db() as con:
            return con.execute("SELECT * FROM courses ORDER BY name").fetchall()

    def set_manual(self, key, on, now=None):
        with self.db() as con:
            con.execute("UPDATE activities SET manual=?, manual_at=? WHERE key=?",
                        (1 if on else 0, (now or time.time()) if on else None, key))
            con.execute("INSERT INTO changes(at, key, kind, after) VALUES (?, ?, 'manual', ?)",
                        (now or time.time(), key, "marcada" if on else "desmarcada"))

    def changes(self, sync_id=None, since=None, kinds=None):
        q, a = "SELECT * FROM changes WHERE 1", []
        if sync_id is not None:
            q += " AND sync_id=?"
            a.append(sync_id)
        if since is not None:
            q += " AND at>=?"
            a.append(since)
        if kinds:
            q += f" AND kind IN ({','.join('?' * len(kinds))})"
            a += list(kinds)
        with self.db() as con:
            return con.execute(q + " ORDER BY id", a).fetchall()

    # --- avisos já dados ---
    def sent(self):
        with self.db() as con:
            return {(r["key"], r["tier"], r["due"]) for r in con.execute("SELECT key, tier, due FROM notifications")}

    def record(self, items, how, now):
        """items: [(chave, tipo, prazo)]. UNIQUE impede aviso repetido para a mesma atividade e o mesmo prazo."""
        with self.db() as con:
            con.executemany("INSERT OR IGNORE INTO notifications(at, key, tier, due, how) VALUES (?, ?, ?, ?, ?)",
                            [(now, k, t, d, how) for k, t, d in items])

    # --- aplicar uma sincronização ---
    def _change(self, con, now, sid, key, kind, before=None, after=None, out=None):
        con.execute("INSERT INTO changes(at, sync_id, key, kind, before, after) VALUES (?, ?, ?, ?, ?, ?)",
                    (now, sid, key, kind, None if before is None else str(before),
                     None if after is None else str(after)))
        if out is not None:
            out.append({"key": key, "kind": kind, "before": before, "after": after})

    def _adopt(self, con, key, rec_events):
        """A atividade já existia só pelo calendário (ev:<id>)? Passa a usar o id do módulo, sem virar "nova"."""
        for eid in rec_events:
            r = con.execute("SELECT key FROM events WHERE id=?", (eid,)).fetchone()
            if r and r["key"] != key and con.execute("SELECT 1 FROM activities WHERE key=?", (r["key"],)).fetchone():
                old = r["key"]
                con.execute("UPDATE activities SET key=? WHERE key=?", (key, old))
                for t in ("changes", "notifications", "events"):
                    con.execute(f"UPDATE {t} SET key=? WHERE key=?", (key, old))
                return con.execute("SELECT * FROM activities WHERE key=?", (key,)).fetchone()
        return None

    def apply(self, res, sid, now):
        """Compara a coleta com o último estado conhecido e grava as diferenças no histórico."""
        out = []
        with self.db() as con:
            first = con.execute("SELECT COUNT(*) FROM activities").fetchone()[0] == 0
            for c in res.courses.values():
                con.execute("INSERT INTO courses(id, name, short, url, past, first_seen, last_seen) "
                            "VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT(id) DO UPDATE SET name=excluded.name, "
                            "short=excluded.short, url=excluded.url, past=excluded.past, last_seen=excluded.last_seen, "
                            "gone_since=NULL", (c["id"], c["name"], c["short"], c["url"], int(c["past"]), now, now))
            if res.courses:
                ids = list(res.courses)
                con.execute(f"UPDATE courses SET gone_since=COALESCE(gone_since, ?) WHERE id NOT IN "
                            f"({','.join('?' * len(ids))})", [now, *ids])
            by_key = {}
            for eid, (key, field) in res.events.items():
                by_key.setdefault(key, []).append(eid)
            for key, rec in res.acts.items():
                if rec["gone"]:
                    continue
                row = con.execute("SELECT * FROM activities WHERE key=?", (key,)).fetchone()
                if row is None:
                    row = self._adopt(con, key, by_key.get(key, []))
                srcs = ",".join(sorted(rec["sources"]))
                if row is None:
                    con.execute("INSERT INTO activities(key, cmid, course, name, mod, kind, summary, open, due, close, "
                                "cutoff, expected, sub, completion, url, sources, first_seen, last_seen, checked_at, "
                                "sync_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                                (key, rec["cmid"], rec["course"], rec["name"], rec["mod"], rec["kind"], rec["summary"],
                                 *(rec[d] for d in DATES), rec["sub"], rec["completion"], rec["url"], srcs, now, now,
                                 now if rec["checked"] else None, sid))
                    if not first:
                        self._change(con, now, sid, key, "nova", None, deadline(rec), out)
                    continue
                new = dict(row)
                for d in DATES:
                    if rec[d] is not None:
                        new[d] = rec[d]
                    elif d == "cutoff":
                        new[d] = None if rec["checked"] else row[d]  # só a página mostra a data limite
                    elif (row[d] and res.cal_ok and res.window[0] <= row[d] < res.window[1]
                          and not any(res.events[e][1] == d for e in by_key.get(key, []))):
                        new[d] = None  # sumiu do calendário no período lido e a página também não mostra
                    # fora isso, na dúvida, mantém o prazo conhecido (nunca some um prazo por falha de leitura)
                if rec["sub"] is not None:
                    new["sub"] = rec["sub"]
                old_dl, new_dl = deadline(row), deadline(new)
                if (old_dl is None) != (new_dl is None) or (old_dl and new_dl and abs(old_dl - new_dl) > 60):
                    self._change(con, now, sid, key, "prazo", old_dl, new_dl, out)
                if row["sub"] != "enviado" and new["sub"] == "enviado":
                    self._change(con, now, sid, key, "entregue", row["sub"], "enviado", out)
                elif row["sub"] == "enviado" and new["sub"] in ("nenhum", "reaberto", "rascunho"):
                    self._change(con, now, sid, key, "reaberta", "enviado", new["sub"], out)
                if row["state"] != "ativa":
                    self._change(con, now, sid, key, "voltou", row["state"], "ativa", out)
                con.execute("UPDATE activities SET cmid=?, course=?, name=?, mod=?, kind=?, summary=?, open=?, due=?, "
                            "close=?, cutoff=?, expected=?, sub=?, completion=?, url=?, sources=?, state='ativa', "
                            "last_seen=?, checked_at=COALESCE(?, checked_at), gone_since=NULL, sync_id=? WHERE key=?",
                            (rec["cmid"] or row["cmid"], rec["course"] or row["course"], rec["name"] or row["name"],
                             rec["mod"] or row["mod"], rec["kind"] if rec["mod"] or rec["kind"] == "evento" else row["kind"],
                             rec["summary"] or row["summary"], *(new[d] for d in DATES), new["sub"],
                             rec["completion"] if rec["completion"] is not None else row["completion"],
                             rec["url"] or row["url"], srcs, now, now if rec["checked"] else None, sid, key))
            for key, verdict in res.missing.items():
                row = con.execute("SELECT state FROM activities WHERE key=?", (key,)).fetchone()
                if verdict == "indisponivel" and row and row["state"] == "ativa":
                    con.execute("UPDATE activities SET state='indisponivel', gone_since=? WHERE key=?", (now, key))
                    self._change(con, now, sid, key, "indisponivel", "ativa", "indisponivel", out)
            for key, rec in res.acts.items():
                if rec["gone"]:
                    row = con.execute("SELECT state FROM activities WHERE key=?", (key,)).fetchone()
                    if row and row["state"] == "ativa":
                        con.execute("UPDATE activities SET state='indisponivel', gone_since=? WHERE key=?", (now, key))
                        self._change(con, now, sid, key, "indisponivel", "ativa", "indisponivel", out)
            con.executemany("INSERT OR REPLACE INTO events(id, key, field) VALUES (?, ?, ?)",
                            [(e, k, f) for e, (k, f) in res.events.items()])
            self._overdue(con, now, sid, out)
        return out, first

    def apply_ical(self, events, sid, now, base=""):
        """Sessão expirada: atualiza só os prazos pelo calendário exportado (status de envio não é conferido)."""
        out = []
        with self.db() as con:
            first = con.execute("SELECT COUNT(*) FROM activities").fetchone()[0] == 0
            shorts = {r["short"]: r["id"] for r in con.execute("SELECT id, short FROM courses")}
            for ev in events:
                m = con.execute("SELECT key, field FROM events WHERE id=?", (ev["id"],)).fetchone()
                key, field = (m["key"], m["field"]) if m else (f"ev:{ev['id']}", "due")
                row = con.execute("SELECT * FROM activities WHERE key=?", (key,)).fetchone()
                if row is None:
                    con.execute("INSERT INTO activities(key, course, name, kind, summary, due, url, sources, first_seen, "
                                "last_seen, sync_id) VALUES (?, ?, ?, 'outro', ?, ?, ?, 'ical', ?, ?, ?)",
                                (key, shorts.get(ev.get("categories")), ev.get("summary", "Evento do calendário"),
                                 (ev.get("description") or "")[:280], ev["start"],
                                 f"{base}/calendar/view.php?view=day&time={int(ev['start'])}", now, now, sid))
                    con.execute("INSERT OR REPLACE INTO events(id, key, field) VALUES (?, ?, ?)", (ev["id"], key, field))
                    if not first:
                        self._change(con, now, sid, key, "nova", None, ev["start"], out)
                    continue
                if row[field] is None or abs(row[field] - ev["start"]) > 60:
                    old_dl = deadline(row)
                    con.execute(f"UPDATE activities SET {field}=?, last_seen=? WHERE key=?", (ev["start"], now, key))
                    new = dict(row)
                    new[field] = ev["start"]
                    if old_dl != deadline(new):
                        self._change(con, now, sid, key, "prazo", old_dl, deadline(new), out)
                else:
                    con.execute("UPDATE activities SET last_seen=? WHERE key=?", (now, key))
            self._overdue(con, now, sid, out)
        return out, first

    def _overdue(self, con, now, sid, out):
        for r in con.execute("SELECT * FROM activities WHERE state='ativa'").fetchall():
            dl = deadline(r)
            if status(r, now) == "atrasada" and not con.execute(
                    "SELECT 1 FROM changes WHERE key=? AND kind='atrasada' AND after=?", (r["key"], str(dl))).fetchone():
                self._change(con, now, sid, r["key"], "atrasada", None, dl, out)
