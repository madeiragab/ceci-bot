"""Monta o retrato das suas atividades a partir da Sala Virtual (só leitura).

Fontes, nesta ordem: disciplinas → Linha do tempo → Calendário (mês a mês) → conteúdo de cada disciplina →
página de cada tarefa/questionário (status de envio). Não depende só da Linha do tempo: tudo que aparece em
qualquer fonte vira uma atividade, identificada pelo id estável do Moodle (cm:<id do módulo>), sem duplicar.
"""
import json
import re
import time

from .clock import local
from .moodle import SessionExpired, SyncError, page_gone, parse_assign, parse_quiz, short, text_of

# recursos (arquivo, link, página...) não têm prazo nem entrega: ficam de fora
RESOURCES = {"resource", "url", "page", "folder", "label", "book", "imscp", "subsection", "qbank"}
KINDS = {"assign": "envio", "quiz": "questionario", "forum": "forum"}
FIELD = {"due": "due", "close": "close", "closesubmission": "close", "open": "open", "opensubmission": "open",
         "expectcompletionon": "expected"}
DATES = ("open", "due", "close", "cutoff", "expected")
PARSERS = {"assign": parse_assign, "quiz": parse_quiz}
MONTHS_BACK, MONTHS_AHEAD = 1, 6
OLD_DONE = 14 * 86400  # entregue e vencida há mais de 14 dias: não precisa reabrir a página
MAX_PAGES = 200


def cmid_from(url):
    m = re.search(r"/mod/\w+/view\.php\?(?:[^\"'#]*&)?id=(\d+)", url or "")
    return int(m.group(1)) if m else None


class Collected:
    def __init__(self):
        self.courses = {}      # id -> {id, name, short, url, past}
        self.scanned = set()   # disciplinas lidas por inteiro
        self.failed = {}       # disciplina -> motivo
        self.acts = {}         # chave -> registro
        self.events = {}       # id do evento -> (chave, campo)
        self.missing = {}      # chave conhecida que sumiu -> "indisponivel" | "existe"
        self.issues = []       # problemas que tornam o resultado parcial
        self.window = (0, 0)   # período coberto pelo calendário
        self.cal_ok = False

    @property
    def partial(self):
        return bool(self.failed or self.issues)

    def rec(self, key, **kw):
        r = self.acts.get(key)
        if r is None:
            r = self.acts[key] = {"key": key, "cmid": None, "course": None, "name": "", "mod": None, "kind": "outro",
                                  "summary": "", "sub": None, "completion": None, "url": None, "sources": set(),
                                  "visible": True, "checked": False, "gone": False, **{d: None for d in DATES}}
        for k, v in kw.items():
            if v is not None and (k not in ("name", "url") or not r.get(k)):
                r[k] = v
        if r["mod"]:
            r["kind"] = KINDS.get(r["mod"], "outro")
        return r


def _months(now):
    d = local(now)
    y, m = d.year, d.month - MONTHS_BACK
    for _ in range(MONTHS_BACK + MONTHS_AHEAD + 1):
        while m < 1:
            y, m = y - 1, m + 12
        while m > 12:
            y, m = y + 1, m - 12
        yield y, m
        m += 1


def _courses(web, res):
    for cls in ("allincludinghidden", "all"):
        try:
            data = web.ajax("core_course_get_enrolled_courses_by_timeline_classification",
                            classification=cls, limit=0, offset=0, sort="fullname")
            break
        except SessionExpired:
            raise
        except SyncError:
            continue
    else:
        raise SyncError("não consegui listar as suas disciplinas", "estrutura")
    try:
        past = {c["id"] for c in web.ajax("core_course_get_enrolled_courses_by_timeline_classification",
                                          classification="past", limit=0, offset=0, sort="fullname")["courses"]}
    except SessionExpired:
        raise
    except SyncError:
        past = set()
    for c in data.get("courses", []):
        res.courses[c["id"]] = {"id": c["id"], "name": text_of(c.get("fullname", "")),
                                "short": text_of(c.get("shortname", "")), "url": c.get("viewurl"),
                                "past": c["id"] in past}


def _event(web, res, ev, source):
    mod, eid = ev.get("modulename") or None, ev.get("id")
    ts = ev.get("timestart") if ev.get("eventtype") != "expectcompletionon" else ev.get("timesort")
    ts = ts or ev.get("timesort")
    course = (ev.get("course") or {}).get("id")
    if mod:
        field, cmid = FIELD.get(ev.get("eventtype")), cmid_from(ev.get("url"))
        if not field or not cmid:
            return  # ex.: "gradingdue" (só professor)
        r = res.rec(f"cm:{cmid}", cmid=cmid, course=course, mod=mod, url=ev.get("url"),
                    name=text_of(ev.get("activityname") or ev.get("name") or ""))
    else:  # evento de disciplina/usuário/site (ex.: "Prova dia 12") — conta como data a lembrar
        field = "due"
        r = res.rec(f"ev:{eid}", course=course, name=text_of(ev.get("name", "")),
                    url=ev.get("viewurl") or f"{web.base}/calendar/view.php?view=day&time={ts}")
        r["kind"] = "evento"
    r[field] = ts
    r["sources"].add(source)
    if ev.get("description") and not r["summary"]:
        r["summary"] = short(text_of(ev["description"]))
    res.events[eid] = (r["key"], field)


def _course_cms(web, cid):
    try:
        st = web.ajax("core_courseformat_get_state", courseid=cid)
        st = json.loads(st) if isinstance(st, str) else st
        return [{"cmid": int(c["id"]), "name": text_of(c.get("name", "")), "mod": c.get("module"),
                 "url": c.get("url"), "visible": bool(c.get("uservisible", True)),
                 "completion": c.get("completionstate") if c.get("istrackeduser") else None}
                for c in st.get("cm", [])]
    except SessionExpired:
        raise
    except (SyncError, ValueError, KeyError, TypeError):
        pass
    status, text = web.page(f"/course/view.php?id={cid}")  # plano B: links da página da disciplina
    if status != 200:
        raise SyncError(f"a página da disciplina respondeu {status}")
    out = {}
    for mod, cmid, inner in re.findall(r'href="[^"]*/mod/(\w+)/view\.php\?id=(\d+)"[^>]*>(.*?)</a>', text, re.S):
        name = text_of(re.sub(r'<span class="accesshide.*?</span>', "", inner, flags=re.S))
        if name and int(cmid) not in out:
            out[int(cmid)] = {"cmid": int(cmid), "name": name, "mod": mod, "visible": True, "completion": None,
                              "url": f"{web.base}/mod/{mod}/view.php?id={cmid}"}
    return list(out.values())


def collect(web, now=None, known=None, progress=None, cancel=None):
    """Lê a Sala Virtual e devolve um Collected. SessionExpired/Offline/ServerDown sobem para quem chamou."""
    now = now or time.time()
    known, progress = known or {}, progress or (lambda *_: None)
    res = Collected()
    cfg = web.open_session()
    progress("disciplinas")
    _courses(web, res)

    progress("linha do tempo")
    try:
        after = 0
        for _ in range(20):
            args = {"timesortfrom": int(now - 60 * 86400), "limitnum": 50, "limittononsuspendedevents": True}
            if after:
                args["aftereventid"] = after
            evs = web.ajax("core_calendar_get_action_events_by_timesort", **args).get("events", [])
            for ev in evs:
                _event(web, res, ev, "linha_do_tempo")
            if len(evs) < 50:
                break
            after = evs[-1]["id"]
    except SessionExpired:
        raise
    except SyncError as e:
        res.issues.append(f"Linha do tempo: {e}")

    progress("calendário")
    months, ok = list(_months(now)), 0
    for y, m in months:
        try:
            d = web.ajax("core_calendar_get_calendar_monthly_view", year=y, month=m, courseid=cfg.get("siteId", 1),
                         categoryid=0, includenavigation=False, mini=True, day=1)
            for w in d.get("weeks", []):
                for day in w.get("days", []):
                    for ev in day.get("events", []):
                        _event(web, res, ev, "calendario")
            ok += 1
        except SessionExpired:
            raise
        except SyncError as e:
            res.issues.append(f"Calendário {m:02d}/{y}: {e}")
    y0, m0 = months[0]
    y1, m1 = months[-1]
    res.window = (local(now).replace(year=y0, month=m0, day=1, hour=0, minute=0).timestamp(),
                  local(now).replace(year=y1 + (m1 == 12), month=m1 % 12 + 1, day=1, hour=0, minute=0).timestamp())
    res.cal_ok = ok == len(months)

    for cid, c in res.courses.items():
        if cancel and cancel():
            raise SyncError("consulta interrompida", "interrompida")
        if c["past"]:
            continue
        progress(f"disciplina {c['short'] or c['name']}")
        try:
            cms = _course_cms(web, cid)
        except SessionExpired:
            raise
        except SyncError as e:
            res.failed[cid] = str(e)
            continue
        for cm in cms:
            if cm["mod"] in RESOURCES or not cm["mod"]:
                continue
            r = res.rec(f"cm:{cm['cmid']}", cmid=cm["cmid"], course=cid, mod=cm["mod"], url=cm["url"],
                        completion=cm["completion"])
            r["name"] = cm["name"] or r["name"]  # nome da disciplina vence o nome do evento ("... vence")
            r["visible"] = cm["visible"]
            r["sources"].add("disciplina")
        res.scanned.add(cid)

    # status de envio: página de cada tarefa e questionário
    pages = 0
    for r in list(res.acts.values()):
        if r["mod"] not in PARSERS or not r["visible"] or not r["cmid"]:
            continue
        old = known.get(r["key"])
        dl = r["due"] or r["close"] or (old and (old["due"] or old["close"])) or 0
        if old and old["sub"] == "enviado" and dl < now - OLD_DONE:
            continue  # entregue há tempo: mantém o que já sabíamos
        if pages >= MAX_PAGES:
            res.issues.append("limite de páginas por consulta atingido")
            break
        if cancel and cancel():
            raise SyncError("consulta interrompida", "interrompida")
        progress(f"atividade {r['name']}")
        pages += 1
        try:
            status, text = web.page(f"/mod/{r['mod']}/view.php?id={r['cmid']}")
        except SessionExpired:
            raise
        except SyncError as e:
            res.issues.append(f"{r['name']}: {e}")
            continue
        if page_gone(status, text):
            r["gone"] = True
            continue
        p = PARSERS[r["mod"]](text)
        if not p["ok"]:
            res.issues.append(f"{r['name']}: página com estrutura diferente da esperada")
            continue
        r["checked"] = True
        r["sub"] = p["sub"]
        r["sources"].add("pagina")
        for f, ts in p["dates"].items():
            if r[f] is None:  # o horário exato do calendário vale mais que o texto da página
                r[f] = ts
        if p["summary"] and not r["summary"]:
            r["summary"] = p["summary"]

    # o que sumiu: investiga antes de dar como indisponível (nunca apaga)
    for key, row in known.items():
        if key in res.acts or row["state"] != "ativa":
            continue
        if key.startswith("ev:"):
            dl = row["due"] or 0
            if res.cal_ok and res.window[0] <= dl < res.window[1]:
                res.missing[key] = "indisponivel"
            continue
        if row["course"] not in res.scanned or not row["cmid"] or not row["mod"]:
            continue
        try:
            status, text = web.page(f"/mod/{row['mod']}/view.php?id={row['cmid']}")
        except SessionExpired:
            raise
        except SyncError:
            continue
        res.missing[key] = "indisponivel" if page_gone(status, text) else "existe"

    # guarda só o necessário: tarefas/questionários sempre; o resto só com data ou conclusão acompanhada
    for key in [k for k, r in res.acts.items()
                if r["mod"] not in PARSERS and r["kind"] != "evento"
                and not any(r[d] for d in DATES) and r["completion"] is None]:
        del res.acts[key]
    return res
