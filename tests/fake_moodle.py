"""Sala Virtual de mentira (Moodle 4 simplificado) em 127.0.0.1, só com dados fictícios, para os testes.

Imita o que a Ceci lê de verdade: Painel (/my/ com M.cfg.sesskey), login, lib/ajax/service.php (disciplinas,
Linha do tempo, calendário mensal, conteúdo da disciplina), páginas de tarefa/questionário e o calendário
exportado (iCal). Nenhuma conta real é usada.
"""
import json
import threading
import urllib.parse
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from ceci.sala.clock import TZ, local

WEEK = ("segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo")
MON = ("jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez")
USER, PASSWORD = "00000000000", "senha-de-teste"  # credenciais falsas, só existem aqui
SESSION, SESSKEY, TOKEN = "sessao-de-teste", "sk-teste", "tok-teste"


def pt_date(ts):
    d = local(ts)
    return f"{WEEK[d.weekday()]}, {d.day} {MON[d.month - 1]}. {d.year}, {d:%H:%M}"


class Fake:
    def __init__(self, now):
        self.now = now
        day = 86400
        self.courses = {101: {"fullname": "Pesquisa Operacional", "shortname": "PO", "past": False},
                        102: {"fullname": "Banco de Dados", "shortname": "BD", "past": False},
                        103: {"fullname": "Ética Profissional", "shortname": "ETI", "past": False},  # sem atividades
                        90: {"fullname": "Cálculo I (2025)", "shortname": "CALC", "past": True}}
        # cmid -> atividade
        self.acts = {
            501: {"course": 101, "mod": "assign", "name": "Lista 3 — Simplex", "due": now + 2 * day + 3600,
                  "open": now - 5 * day, "status": "new"},
            502: {"course": 101, "mod": "quiz", "name": "Questionário 2", "close": now + 6 * day, "state": None},
            503: {"course": 102, "mod": "assign", "name": "Modelo ER", "due": now + 10 * day, "status": "draft"},
            504: {"course": 102, "mod": "assign", "name": "Relatório sem data", "status": "new"},
            505: {"course": 102, "mod": "forum", "name": "Fórum de apresentação", "due": now + 4 * day},
            506: {"course": 102, "mod": "resource", "name": "Slides aula 1"},
            507: {"course": 101, "mod": "forum", "name": "Avisos"},  # sem prazo, sem conclusão: fica de fora
        }
        self.course_events = [{"id": 9001, "course": 101, "name": "Prova 1", "time": now + 12 * day}]
        self.valid = {SESSION}
        self.down = False
        self.fail_course = set()
        self.gone = set()
        self.ical_extra = []
        self.requests = 0
        self.base = ""

    # --- eventos no formato do exporter do Moodle ---
    def events(self):
        out = []
        for cmid, a in self.acts.items():
            if cmid in self.gone:
                continue
            types = {"assign": [("due", "due")], "quiz": [("close", "close")], "forum": [("due", "due")]}
            for field, etype in types.get(a["mod"], []):
                if a.get(field):
                    out.append({"id": cmid * 10 + (1 if field == "due" else 2), "name": f"{a['name']} vence",
                                "activityname": a["name"], "modulename": a["mod"], "instance": cmid * 7,
                                "eventtype": etype, "timestart": int(a[field]), "timesort": int(a[field]),
                                "course": {"id": a["course"]}, "description": f"<p>Instruções de {a['name']}</p>",
                                "url": f"{self.base}/mod/{a['mod']}/view.php?id={cmid}",
                                "_action": a["mod"] in ("assign", "quiz") and a.get("status") != "submitted"
                                and a.get("state") != "finished"})
        for e in self.course_events:
            out.append({"id": e["id"], "name": e["name"], "modulename": None, "eventtype": "course",
                        "timestart": int(e["time"]), "timesort": int(e["time"]), "course": {"id": e["course"]},
                        "description": "", "url": "", "_action": False})
        return sorted(out, key=lambda e: (e["timesort"], e["id"]))


class Handler(BaseHTTPRequestHandler):
    fake = None

    def log_message(self, *a):
        pass

    def _send(self, code, body="", ctype="text/html; charset=utf-8", headers=()):
        data = body.encode() if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        for k, v in headers:
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def _logged(self):
        ck = self.headers.get("Cookie", "")
        return any(p.strip() == f"MoodleSession={s}" for s in self.fake.valid for p in ck.split(";"))

    def _page(self, body, cls="pagelayout-standard"):
        cfg = json.dumps({"wwwroot": self.fake.base, "sesskey": SESSKEY, "siteId": 1, "sessiontimeout": "28800"})
        return (f"<html><head><script>var M = {{}}; M.cfg = {cfg};</script></head><body id='page' class='{cls}'>{body}"
                "</body></html>")

    def do_GET(self):
        self.handle_req("GET")

    def do_POST(self):
        self.handle_req("POST")

    def handle_req(self, method):
        f = self.fake
        f.requests += 1
        u = urllib.parse.urlsplit(self.path)
        q = dict(urllib.parse.parse_qsl(u.query))
        body = self.rfile.read(int(self.headers.get("Content-Length") or 0)) if method == "POST" else b""
        if f.down:
            return self._send(503, "Serviço indisponível")
        path = u.path
        if path == "/calendar/export_execute.php":
            return self._ical(q)
        if path == "/login/index.php":
            if method == "POST":
                form = dict(urllib.parse.parse_qsl(body.decode()))
                if form.get("username") == USER and form.get("password") == PASSWORD:
                    return self._send(303, "", headers=[("Location", "/my/"),
                                                        ("Set-Cookie", f"MoodleSession={SESSION}; Path=/; HttpOnly")])
            form = ("<form id='login' method='post' action='/login/index.php'>"
                    "<input type='text' name='username' id='username' placeholder='CPF sem ponto e traço'>"
                    "<input type='password' name='password' id='password'>"
                    "<button type='submit' id='loginbtn'>Acessar</button></form>")
            return self._send(200, self._page(form, "notloggedin pagelayout-login"))
        if not self._logged():
            if path == "/lib/ajax/service.php":
                return self._send(200, json.dumps({"error": "Sessão expirada", "errorcode": "servicerequireslogin"}),
                                  "application/json")
            return self._send(303, "", headers=[("Location", "/login/index.php")])
        if path == "/my/":
            return self._send(200, self._page("<h1>Painel</h1>", "pagelayout-mydashboard"))
        if path == "/login/logout.php":
            f.valid.discard(SESSION)
            return self._send(303, "", headers=[("Location", "/")])
        if path == "/lib/ajax/service.php":
            return self._ajax(q, json.loads(body or b"[]"))
        if path.startswith("/mod/") and path.endswith("/view.php"):
            return self._mod(path.split("/")[2], int(q.get("id", 0)))
        if path == "/course/view.php":
            cid = int(q.get("id", 0))
            if cid in f.fail_course:
                return self._send(403, self._page("<div class='box errorbox'>Sem acesso</div>"))
            links = "".join(f"<a href='{f.base}/mod/{a['mod']}/view.php?id={c}'>{a['name']}</a>"
                            for c, a in f.acts.items() if a["course"] == cid and c not in f.gone)
            return self._send(200, self._page(links))
        if path == "/calendar/export.php":
            if method == "POST":
                url = (f"{f.base}/calendar/export_execute.php?userid=2&amp;authtoken={TOKEN}&amp;preset_what=all"
                       f"&amp;preset_time=recentupcoming")
                return self._send(200, self._page(f"<input id='calendarexporturl' value='{url}'>"))
            return self._send(200, self._page("<form><input type='hidden' name='_qf__core_calendar_export_form' "
                                              "value='1'></form>"))
        return self._send(404, self._page("<div class='box errorbox'>Página não encontrada</div>"))

    def _ajax(self, q, calls):
        f = self.fake
        c = calls[0]
        m, a = c["methodname"], c["args"]
        if q.get("sesskey") != SESSKEY:
            return self._send(200, json.dumps([{"error": True, "exception": {"errorcode": "invalidsesskey"}}]),
                              "application/json")
        data = None
        if m == "core_course_get_enrolled_courses_by_timeline_classification":
            past = a["classification"] == "past"
            data = {"courses": [{"id": i, "fullname": c["fullname"], "shortname": c["shortname"],
                                 "viewurl": f"{f.base}/course/view.php?id={i}"}
                                for i, c in f.courses.items() if not past or c["past"]], "nextoffset": 0}
        elif m == "core_calendar_get_action_events_by_timesort":
            evs = [e for e in f.events() if e["_action"] and e["timesort"] >= a["timesortfrom"]]
            if a.get("aftereventid"):
                ids = [e["id"] for e in evs]
                evs = evs[ids.index(a["aftereventid"]) + 1:] if a["aftereventid"] in ids else []
            data = {"events": evs[:a.get("limitnum", 50)]}
        elif m == "core_calendar_get_calendar_monthly_view":
            evs = [e for e in f.events() if (local(e["timestart"]).year, local(e["timestart"]).month)
                   == (a["year"], a["month"])]
            data = {"weeks": [{"days": [{"events": evs}]}]}
        elif m == "core_courseformat_get_state":
            cid = a["courseid"]
            if cid in f.fail_course:
                return self._send(200, json.dumps([{"error": True, "exception": {"errorcode": "nopermissions",
                                                                                  "message": "Sem permissão"}}]),
                                  "application/json")
            cms = [{"id": str(c), "name": x["name"], "module": x["mod"], "uservisible": True,
                    "url": f"{f.base}/mod/{x['mod']}/view.php?id={c}", "istrackeduser": False}
                   for c, x in f.acts.items() if x["course"] == cid and c not in f.gone]
            data = json.dumps({"course": {"id": cid}, "section": [], "cm": cms})
        if data is None:
            return self._send(200, json.dumps([{"error": True, "exception": {"errorcode": "invalidrecord"}}]),
                              "application/json")
        return self._send(200, json.dumps([{"error": False, "data": data}]), "application/json")

    def _mod(self, mod, cmid):
        f = self.fake
        a = f.acts.get(cmid)
        if not a or cmid in f.gone or a["mod"] != mod:
            return self._send(404, self._page("<div class='box errorbox'>Não foi possível encontrar o registro</div>"))
        dates = ""
        for field, label in (("open", "Aberto"), ("due", "Vencimento"), ("close", "Fecha")):
            if a.get(field):
                dates += f"<div><strong>{label}:</strong> {pt_date(a[field])}</div>"
        body = f"<h2>{a['name']}</h2><div data-region='activity-dates'>{dates}</div>"
        if mod == "assign":
            st = a.get("status")
            cell = {"new": "Nenhum envio foi feito ainda", "draft": "Rascunho (não enviado)",
                    "submitted": "Enviado para avaliação", "reopened": "Reaberto"}.get(st, "Nenhuma tentativa")
            cls = f" class='submissionstatus{st} cell c1'" if st else ""
            body += (f"<div id='intro'><div>Instruções de {a['name']}</div></div><table class='submissionstatustable'>"
                     f"<tr><th>Status de envio</th><td{cls}>{cell}</td></tr></table>")
        elif mod == "quiz":
            if a.get("state"):
                body += ("<table class='quizattemptsummary'><tr><td>"
                         + ("Finalizada" if a["state"] == "finished" else "Em andamento") + "</td></tr></table>")
            else:
                body += "<div class='quizinfo'></div><button>Tentar responder o questionário agora</button>"
        return self._send(200, self._page(body))

    def _ical(self, q):
        f = self.fake
        if q.get("authtoken") != TOKEN:
            return self._send(403, "token inválido")
        lines = ["BEGIN:VCALENDAR", "VERSION:2.0"]
        for e in f.events() + f.ical_extra:
            ts = datetime.fromtimestamp(e["timestart"], TZ).astimezone(timezone.utc)
            lines += ["BEGIN:VEVENT", f"UID:{e['id']}@127.0.0.1", f"SUMMARY:{e['name']}",
                      f"DTSTART:{ts:%Y%m%dT%H%M%SZ}",
                      f"CATEGORIES:{f.courses[e['course']['id']]['shortname']}", "END:VEVENT"]
        lines.append("END:VCALENDAR")
        return self._send(200, "\r\n".join(lines), "text/calendar; charset=utf-8")


def serve(fake):
    handler = type("H", (Handler,), {"fake": fake})
    srv = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    fake.base = f"http://127.0.0.1:{srv.server_address[1]}"
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv
