"""Leitura da Sala Virtual (Moodle 4) pela interface web, com a sessão do seu próprio login.

A instituição deixou os web services desligados (tool_mobile_get_public_config: enablewebservices 0), então
não existe token de API para aluno. O que qualquer aluno logado tem é o mesmo canal que o Painel usa: as
chamadas AJAX de lib/ajax/service.php (Linha do tempo, Calendário, disciplinas) e as páginas das atividades.
Tudo aqui é só leitura: nada envia, responde, tenta questionário ou altera coisa alguma.
"""
import html
import http.cookiejar
import json
import re
import socket
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from .clock import TZ

DEFAULT_URL = "https://salavirtual2.muz.ifsuldeminas.edu.br"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) CeciBot"
LOGIN_CODES = {"servicerequireslogin", "invalidsesskey", "requireloginerror", "sessionerroruser", "sessionexpired"}


class SyncError(Exception):
    kind = "falhou"

    def __init__(self, msg, kind=None):
        super().__init__(msg)
        if kind:
            self.kind = kind


class SessionExpired(SyncError):
    kind = "sessao"


class Offline(SyncError):
    kind = "sem_internet"


class ServerDown(SyncError):
    kind = "servidor"


def _net_error(reason):
    if isinstance(reason, socket.gaierror) or getattr(reason, "winerror", None) in (10051, 10065, 11001, 11004):
        return Offline("sem conexão com a internet (o endereço da Sala Virtual não foi encontrado)")
    if isinstance(reason, (TimeoutError, socket.timeout)):
        return ServerDown("a Sala Virtual não respondeu a tempo")
    if isinstance(reason, ConnectionRefusedError):
        return ServerDown("a Sala Virtual recusou a conexão")
    if isinstance(reason, ssl.SSLError):
        return ServerDown("falha na conexão segura (certificado) com a Sala Virtual")
    return ServerDown(f"falha de conexão ({type(reason).__name__})")


def _cookie(c):
    exp = c.get("expires")
    return http.cookiejar.Cookie(
        0, c["name"], c["value"], None, False, c["domain"], True, c["domain"].startswith("."), c.get("path", "/"),
        True, bool(c.get("secure")), int(exp) if exp and exp > 0 else None, False, None, None,
        {"HttpOnly": None} if c.get("httpOnly") else {})


def safe_url(url):
    """Para logs: sem sesskey, authtoken nem qualquer parâmetro."""
    return (url or "").split("?")[0]


def _is_login(url):
    return "/login/index.php" in urllib.parse.urlsplit(url).path


class MoodleWeb:
    """Cliente HTTP mínimo (urllib) que fala com a Sala Virtual usando os cookies do seu login."""

    def __init__(self, base, cookies=(), ua=None, timeout=25, delay=0.0):
        self.base = base.rstrip("/")
        self.host = urllib.parse.urlsplit(self.base).hostname
        self.jar = http.cookiejar.CookieJar()
        for c in cookies:
            self.jar.set_cookie(_cookie(c))
        self.op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))
        self.ua, self.timeout, self.delay = ua or UA, timeout, delay
        self.sesskey, self.cfg, self.requests = None, {}, 0

    def _open(self, path, data=None, ctype=None):
        url = path if path.startswith("http") else self.base + path
        if urllib.parse.urlsplit(url).hostname != self.host:
            raise SyncError("endereço fora da Sala Virtual")
        headers = {"User-Agent": self.ua}
        if ctype:
            headers["Content-Type"] = ctype
        if self.delay and self.requests:
            time.sleep(self.delay)  # educado com o servidor da escola
        self.requests += 1
        try:
            with self.op.open(urllib.request.Request(url, data=data, headers=headers), timeout=self.timeout) as r:
                return r.status, r.geturl(), r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            if e.code >= 500:
                raise ServerDown(f"a Sala Virtual respondeu com erro {e.code}")
            return e.code, e.geturl(), e.read().decode("utf-8", "replace")
        except urllib.error.URLError as e:
            raise _net_error(e.reason)
        except (TimeoutError, socket.timeout, ConnectionError, ssl.SSLError) as e:
            raise _net_error(e)

    def page(self, path, form=None):
        data = urllib.parse.urlencode(form).encode() if form else None
        status, url, text = self._open(path, data, "application/x-www-form-urlencoded" if form else None)
        if _is_login(url) and not _is_login(path):
            raise SessionExpired("a sessão da Sala Virtual expirou")
        return status, text

    def open_session(self):
        """Abre o Painel; sem sessão válida o Moodle manda para o login."""
        status, text = self.page("/my/")
        cfg = parse_cfg(text)
        if "notloggedin" in body_classes(text) or "guest" in body_classes(text):
            raise SessionExpired("a sessão da Sala Virtual expirou")
        if status != 200 or not cfg.get("sesskey"):
            raise SyncError("o Painel da Sala Virtual veio diferente do esperado (estrutura mudou?)", "estrutura")
        self.cfg, self.sesskey = cfg, cfg["sesskey"]
        return cfg

    def ajax(self, method, **args):
        """Mesma chamada que as páginas do Moodle fazem (lib/ajax/service.php) — só funções de leitura."""
        body = json.dumps([{"index": 0, "methodname": method, "args": args}]).encode()
        q = urllib.parse.urlencode({"sesskey": self.sesskey or "", "info": method})
        status, url, text = self._open(f"/lib/ajax/service.php?{q}", body, "application/json")
        try:
            r = json.loads(text)
        except ValueError:
            raise SyncError(f"{method}: resposta inesperada ({status})", "estrutura")
        if isinstance(r, list) and r and not r[0].get("error"):
            return r[0].get("data")
        err = r if isinstance(r, dict) else ((r[0].get("exception") or {}) if r else {})
        code = err.get("errorcode", "")
        if code in LOGIN_CODES:
            raise SessionExpired("a sessão da Sala Virtual expirou")
        raise SyncError(f"{method}: {err.get('message') or err.get('error') or code or 'erro'}", "ajax")


# --- páginas -------------------------------------------------------------------------------------------
def parse_cfg(text):
    m = re.search(r"M\.cfg\s*=\s*(\{.*?\})\s*;", text, re.S)
    try:
        return json.loads(m.group(1)) if m else {}
    except ValueError:
        return {}


def body_classes(text):
    m = re.search(r"<body[^>]*\bclass=\"([^\"]*)\"", text)
    return set(m.group(1).split()) if m else set()


def text_of(fragment):
    t = re.sub(r"<(script|style)\b.*?</\1>", " ", fragment or "", flags=re.S | re.I)
    t = re.sub(r"<br\s*/?>|</p>|</div>|</li>", "\n", t, flags=re.I)
    t = html.unescape(re.sub(r"<[^>]+>", " ", t))
    return re.sub(r"[ \t\r\f\v]+", " ", re.sub(r"\s*\n\s*", "\n", t)).strip()


def short(text, n=280):
    t = " ".join((text or "").split())
    return t if len(t) <= n else t[:n - 1].rsplit(" ", 1)[0] + "…"


MONTHS = {"jan": 1, "fev": 2, "feb": 2, "mar": 3, "abr": 4, "apr": 4, "mai": 5, "may": 5, "jun": 6, "jul": 7,
          "ago": 8, "aug": 8, "set": 9, "sep": 9, "out": 10, "oct": 10, "nov": 11, "dez": 12, "dec": 12}
DATE_RE = re.compile(r"(\d{1,2})\s+(?:de\s+)?([a-zà-ÿ]{3})[a-zà-ÿ]*\.?\s+(?:de\s+)?(\d{4}),?\s+(?:às\s+)?"
                     r"(\d{1,2}):(\d{2})\s*(am|pm)?", re.I)
# rótulo (minúsculo) -> campo. Ordem importa: "data limite" antes de "data de entrega".
LABELS = (("limite", "cutoff"), ("cut-off", "cutoff"), ("vencimento", "due"), ("entrega", "due"), ("due", "due"),
          ("fech", "close"), ("encerr", "close"), ("close", "close"), ("conclusão esperada", "expected"),
          ("expected", "expected"), ("ab", "open"), ("open", "open"), ("disponível a partir", "open"))


def parse_date(s):
    m = DATE_RE.search(s or "")
    if not m or m.group(2)[:3].lower() not in MONTHS:
        return None
    d, mon, y, h, mi, ap = m.groups()
    h = int(h) % 12 + (12 if ap.lower() == "pm" else 0) if ap else int(h)
    return datetime(int(y), MONTHS[mon[:3].lower()], int(d), h, int(mi), tzinfo=TZ).timestamp()


def _field(label):
    lab = label.lower().strip()
    for k, f in LABELS:
        if lab.startswith(k) or (len(k) > 3 and k in lab):
            return f
    return None


def parse_dates(text):
    """Datas mostradas na página da atividade (cabeçalho "activity-dates" e tabela de status)."""
    out = {}
    i = text.find('data-region="activity-dates"')
    chunks = [text[i:i + 3000]] if i >= 0 else []
    j = text.find("submissionstatustable")
    if j >= 0:
        chunks.append(text[j:j + 8000])
    for chunk in chunks:
        pairs = re.findall(r"<strong>\s*([^<]{2,40}?)\s*:?\s*</strong>\s*([^<]{6,80})", chunk)
        pairs += re.findall(r"<th[^>]*>\s*([^<]{3,40}?)\s*</th>\s*<td[^>]*>\s*([^<]{6,80})", chunk)
        for label, value in pairs:
            f, ts = _field(label.rstrip(":")), parse_date(value)
            if f and ts and f not in out:
                out[f] = ts
    return out


def page_gone(status, text):
    """Atividade removida, oculta ou sem acesso (erro do Moodle no lugar da página)."""
    return status in (403, 404) or "errorbox" in text


SUB_CLASS = {"submitted": "enviado", "draft": "rascunho", "new": "nenhum", "reopened": "reaberto"}
SUB_TEXT = (("enviado para avalia", "enviado"), ("submitted for grading", "enviado"),
            ("rascunho", "rascunho"), ("draft (not submitted)", "rascunho"), ("nenhuma tentativa", "nenhum"),
            ("no attempt", "nenhum"), ("nenhum envio", "nenhum"), ("no submissions have been made", "nenhum"),
            ("reaberto", "reaberto"), ("reopened", "reaberto"))


def parse_assign(text):
    """Status de envio da tarefa como o próprio Moodle mostra para você."""
    sub = None
    m = re.search(r"class=\"[^\"]*\bsubmissionstatus(submitted|draft|new|reopened)\b", text)
    if m:
        sub = SUB_CLASS[m.group(1)]
    else:
        m = re.search(r"(?:Status de envio|Submission status)\s*</t[hd]>\s*<td[^>]*>(.*?)</td>", text, re.S | re.I)
        if m:
            cell = text_of(m.group(1)).lower()
            sub = next((v for k, v in SUB_TEXT if k in cell), None)
    intro = re.search(r"id=\"intro\"[^>]*>(.*?)</div>\s*</div>", text, re.S)
    ok = sub is not None or "submissionstatustable" in text
    return {"sub": sub, "dates": parse_dates(text), "summary": short(text_of(intro.group(1))) if intro else "",
            "ok": ok}


def parse_quiz(text):
    """Questionário: tentativa finalizada = enviado; em andamento = ainda não finalizado.

    Moodle 4.x (a Sala Virtual): um cartão por tentativa com a tabela `quizreviewsummary` ("Situação: Finalizada").
    Moodle antigo: uma tabela `quizattemptsummary` com todas."""
    tables = re.findall(r"quiz(?:attempt|review)summary(.*?)</table>", text, re.S)
    t = " ".join(text_of(x) for x in tables).lower()
    if re.search(r"finalizad|finished|submitted", t):
        sub = "enviado"
    elif re.search(r"em andamento|in progress|atrasad|overdue", t):
        sub = "rascunho"
    elif tables or "quizstartbuttondiv" in text or re.search(
            r"tentar responder|iniciar tentativa|fazer uma tentativa|tentativa do question|attempt quiz", text, re.I):
        sub = "nenhum"
    else:
        sub = None
    ok = sub is not None or "quizinfo" in text or "activity-dates" in text
    return {"sub": sub, "dates": parse_dates(text), "summary": "", "ok": ok}


# --- calendário exportado (iCal) --------------------------------------------------------------------------
def _ical_ts(value, params):
    v = value.strip()
    try:
        if v.endswith("Z"):
            return datetime.strptime(v, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc).timestamp()
        if "VALUE=DATE" in params or len(v) == 8:
            return datetime.strptime(v[:8], "%Y%m%d").replace(hour=23, minute=59, tzinfo=TZ).timestamp()
        return datetime.strptime(v[:15], "%Y%m%dT%H%M%S").replace(tzinfo=TZ).timestamp()
    except ValueError:
        return None


def parse_ical(text):
    lines = []
    for raw in text.replace("\r\n", "\n").split("\n"):
        if raw[:1] in (" ", "\t") and lines:
            lines[-1] += raw[1:]
        else:
            lines.append(raw)
    events, cur = [], None
    for ln in lines:
        if ln == "BEGIN:VEVENT":
            cur = {}
        elif ln == "END:VEVENT" and cur is not None:
            m = re.match(r"(\d+)@", cur.get("uid", ""))
            if m and cur.get("start"):
                cur["id"] = int(m.group(1))
                events.append(cur)
            cur = None
        elif cur is not None and ":" in ln:
            key, value = ln.split(":", 1)
            name, _, params = key.partition(";")
            value = value.replace("\\n", "\n").replace("\\,", ",").replace("\\;", ";").replace("\\\\", "\\")
            name = name.upper()
            if name == "DTSTART":
                cur["start"] = _ical_ts(value, params)
            elif name in ("UID", "SUMMARY", "DESCRIPTION", "CATEGORIES"):
                cur[name.lower()] = value
    return events


def fetch_ical(url, timeout=25):
    """Calendário exportado do Moodle: link próprio (com chave), funciona mesmo com a sessão expirada."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            text = r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        raise ServerDown(f"o calendário exportado respondeu {e.code}")
    except urllib.error.URLError as e:
        raise _net_error(e.reason)
    except (TimeoutError, socket.timeout, ConnectionError, ssl.SSLError) as e:
        raise _net_error(e)
    if "BEGIN:VCALENDAR" not in text:
        raise SyncError("o calendário exportado não veio no formato esperado", "estrutura")
    return parse_ical(text)


def ical_url(web):
    """Pede ao Moodle o link do calendário exportado (formulário "Obter URL do calendário"; nada é alterado)."""
    status, text = web.page("/calendar/export.php")
    qf = re.search(r'name="(_qf__[^"]+)"', text)
    if status != 200 or not qf:
        return None
    form = {"sesskey": web.sesskey, qf.group(1): "1", "events[exportevents]": "all",
            "period[timeperiod]": "recentupcoming", "generateurl": "1"}
    status, text = web.page("/calendar/export.php", form)
    m = re.search(r"(https?://[^\"'<>\s]+/calendar/export_execute\.php\?[^\"'<>\s]+)", html.unescape(text))
    return m.group(1) if m else None
