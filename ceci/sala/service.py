"""Orquestra a Sala Virtual: uma consulta automática por dia, consultas manuais, login e lembretes locais.

Entre uma consulta e outra não roda nada: nenhum navegador, nenhuma checagem de internet. Um único timer
local acorda no próximo lembrete (ou no horário da consulta diária) e volta a dormir.
"""
import logging
import os
import re
import threading
import time
import traceback

from PySide6.QtCore import QObject, QTimer, Signal

from ..settings import CONFIG_DIR
from . import protect
from .clock import at, in_window, today
from .collect import collect
from .moodle import MoodleWeb, SessionExpired, SyncError, fetch_ical, ical_url
from .reminders import IMPORTANT, due_now
from .store import Store, deadline

LOG = os.path.join(CONFIG_DIR, "sala_virtual.log")
STARTUP_DELAY = 20_000  # ms: a Ceci entra na tela antes da consulta pendente do dia e dos lembretes
MAX_SLEEP = 3 * 3600    # s: reavalia os lembretes (só dados locais) no máximo a cada 3 h
FS_RETRY = 300          # s: em tela cheia, tenta mostrar de novo depois de 5 min
NOTIFY = {"nova": "nova", "prazo": "prazo_alterado", "entregue": "entregue"}


def _clean(text):
    """Logs nunca levam sesskey, authtoken nem cookies."""
    return re.sub(r"(sesskey|authtoken|MoodleSession\w*)=[^&\s\"']+", r"\1=***", str(text))


def _logger():
    lg = logging.getLogger("ceci.sala")
    if not lg.handlers:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        h = logging.FileHandler(LOG, encoding="utf8")
        h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        lg.addHandler(h)
        lg.setLevel(logging.INFO)
    return lg


class SalaVirtual(QObject):
    progress = Signal(str)       # "conferindo" | "atualizando"
    finished = Signal(dict)      # resultado de uma consulta
    alerts = Signal(dict)        # avisos para mostrar agora
    login_done = Signal(bool, str)
    changed = Signal()           # dados ou conexão mudaram (janelas se atualizam)
    _done = Signal(object)       # da thread de trabalho para a thread principal

    def __init__(self, store=None, clock=time.time, is_fullscreen=lambda: False, session=protect, login_fn=None,
                 startup_delay=STARTUP_DELAY):
        super().__init__()
        self.store = store or Store()
        self.now, self.is_fullscreen, self.session = clock, is_fullscreen, session
        self.login_fn, self.startup_delay = login_fn, startup_delay
        self.busy = None  # "sync" | "login"
        self.stop = False
        self.next_reminder, self.deferred = None, None
        self.timer = QTimer(self, singleShot=True, timeout=self._wake)
        self._done.connect(self._on_done)
        self.log = _logger()

    # --- estado ---
    def connected(self):
        return self.session.load() is not None

    def auto_due(self, now=None):
        """A tentativa automática de hoje ainda não aconteceu e o horário já passou?"""
        now = now or self.now()
        return (self.connected() and self.store.last_auto_day() != today(now)
                and now >= at(now, self.store.prefs()["auto_time"]))

    def session_expired(self):
        last, ok = self.store.last_sync(), self.store.last_success(full=True)
        return bool(last and last["kind"] == "sessao" and (not ok or ok["id"] < last["id"]))

    def start(self):
        self.store.mark_interrupted()
        QTimer.singleShot(self.startup_delay, self._wake)

    def shutdown(self):
        self.stop = True
        self.timer.stop()

    # --- consultas ---
    def sync(self, trigger="manual"):
        if self.busy:
            return False
        sess = self.session.load()
        if not sess:
            self.finished.emit({"trigger": trigger, "result": "desconectada", "kind": "desconectada",
                                "message": "A Sala Virtual não está conectada.", "changes": []})
            return False
        now = self.now()
        sid = self.store.begin_sync(trigger, now)  # a tentativa fica registrada já aqui (1 automática por dia)
        self.busy, self.stop = "sync", False
        self.progress.emit("conferindo")
        base = self.store.prefs()["url"]
        threading.Thread(target=self._sync_worker, args=(sid, trigger, sess, base), daemon=True).start()
        return True

    def _sync_worker(self, sid, trigger, sess, base):
        out = {"trigger": trigger, "sid": sid, "changes": [], "first": False, "issues": [], "failed": {}}
        counts = (0, 0, 0)
        try:
            web = MoodleWeb(base, sess.get("cookies", []), sess.get("ua"), delay=0.15)
            res = collect(web, self.now(), self.store.known(), cancel=lambda: self.stop)
            self._done.emit(("progress", "atualizando"))
            out["changes"], out["first"] = self.store.apply(res, sid, self.now())
            active = [c for c in res.courses.values() if not c["past"]]
            counts = (len(active), len(res.scanned), len(res.acts))
            out.update(issues=res.issues[:20], failed=res.failed)
            if res.partial:
                bits = []
                if res.failed:
                    bits.append(f"{len(res.failed)} de {len(active)} disciplinas não puderam ser lidas")
                if res.issues:
                    bits.append(f"{len(res.issues)} problema(s) de leitura")
                out.update(result="parcial", kind="parcial", message="Consulta parcial: " + "; ".join(bits) + ".")
            else:
                out.update(result="ok", kind="ok",
                           message=f"Conferi {len(res.scanned)} disciplinas e {len(res.acts)} atividades.")
        except SessionExpired:
            out.update(result="falhou", kind="sessao",
                       message="A sessão da Sala Virtual expirou: entre de novo para eu conferir os envios.")
            if sess.get("ical"):
                try:
                    evs = fetch_ical(sess["ical"])
                    out["changes"], out["first"] = self.store.apply_ical(evs, sid, self.now(), base)
                    out.update(result="parcial", message="A sessão expirou: conferi só os prazos pelo calendário "
                                                         "exportado. O status de envio não foi conferido.")
                except SyncError as e:
                    self.log.warning("calendário exportado: %s", _clean(e))
        except SyncError as e:
            out.update(result="falhou", kind=e.kind, message=str(e))
        except Exception as e:  # nunca afirma sucesso: registra e avisa a falha
            self.log.error("erro inesperado: %s", _clean(traceback.format_exc()))
            out.update(result="falhou", kind="falhou", message=f"Erro inesperado na consulta ({type(e).__name__}).")
        self.store.finish_sync(sid, out["result"], out["kind"], out["message"], self.now(), *counts)
        self.log.info("consulta %s #%s: %s (%s) %s", trigger, sid, out["result"], out["kind"], _clean(out["message"]))
        for i in out["issues"]:
            self.log.info("  %s", _clean(i))
        self._done.emit(("sync", out))

    # --- conexão ---
    def connect_account(self):
        if self.busy:
            return False
        self.busy, self.stop = "login", False
        threading.Thread(target=self._login_worker, args=(self.store.prefs()["url"],), daemon=True).start()
        return True

    def _login_worker(self, base):
        from .login import LoginCancelled, login
        try:
            got = (self.login_fn or login)(base, cancel=lambda: self.stop)
            web = MoodleWeb(base, got["cookies"], got["ua"])
            web.open_session()
            try:
                ical = ical_url(web)
            except SyncError:
                ical = None
            self.session.save({"base": base, "cookies": got["cookies"], "ua": got["ua"], "ical": ical,
                               "saved": time.time()})
            self.log.info("conectada (calendário exportado: %s)", "sim" if ical else "não")
            res = (True, "Sala Virtual conectada.")
        except LoginCancelled as e:
            res = (False, str(e).capitalize() + ".")
        except SessionExpired:
            res = (False, "A Sala Virtual não reconheceu o login (entrou como visitante?). Entre com o seu CPF.")
        except SyncError as e:
            res = (False, f"Não consegui confirmar o login: {e}.")
        except Exception as e:
            self.log.error("login: %s", _clean(traceback.format_exc()))
            res = (False, f"Não consegui abrir o login: {_clean(e)}")
        self._done.emit(("login", res))

    def disconnect(self):
        """Apaga a sessão local e, se ainda valer, encerra a sessão no Moodle."""
        sess = self.session.load()
        self.session.clear()
        self.changed.emit()
        if sess:
            threading.Thread(target=self._logout, args=(sess,), daemon=True).start()

    def _logout(self, sess):
        try:
            web = MoodleWeb(sess.get("base") or self.store.prefs()["url"], sess.get("cookies", []), sess.get("ua"),
                            timeout=10)
            web.open_session()
            web.page(f"/login/logout.php?sesskey={web.sesskey}")
        except Exception:
            pass

    # --- volta para a thread principal ---
    def _on_done(self, item):
        kind, data = item
        if kind == "progress":
            self.progress.emit(data)
            return
        self.busy = None
        if kind == "sync":
            self.finished.emit(data)
            self.changed.emit()
            self._remind(data)
            self._arm()
        elif kind == "login":
            self.login_done.emit(*data)
            self.changed.emit()
            if data[0]:
                self.sync("manual")  # conectou: já lê disciplinas e atividades (não gasta a automática)

    # --- lembretes ---
    def reschedule(self):
        """Preferências mudaram: recalcula o próximo lembrete/horário (sem avisar nada agora)."""
        _, _, self.next_reminder = due_now(self.store.rows(), self.store.prefs(), self.now(), self.store.sent())
        self._arm()

    def _wake(self):
        if not self.busy and self.auto_due():
            self.sync("auto")
        else:
            self._remind()
            self._arm()

    def _remind(self, sync=None):
        now, prefs = self.now(), self.store.prefs()
        rows = self.store.rows()
        by_key, sent = {r["key"]: r for r in rows}, self.store.sent()
        items = []
        if sync and not sync.get("first"):  # novidades desta consulta (a primeira vira um resumo)
            for c in sync["changes"]:
                r, tier = by_key.get(c["key"]), NOTIFY.get(c["kind"])
                if r and tier and (r["key"], tier, deadline(r)) not in sent:
                    items.append({"row": dict(r), "tier": tier})
        fire, skip, self.next_reminder = due_now(rows, prefs, now, sent)
        noted = {i["row"]["key"] for i in items if i["tier"] == "nova"}
        quiet = prefs["quiet"] and in_window(now, prefs["quiet_start"], prefs["quiet_end"])
        fs = self.is_fullscreen()
        self.deferred = None
        for r, tier in fire:
            if r["key"] in noted:  # o aviso de "nova" já mostra o prazo: não duplica
                skip.append((r["key"], tier, deadline(r)))
                continue
            important = tier in IMPORTANT
            if quiet and not (important and prefs["urgent_quiet"]):
                self.deferred = "quiet"
                continue
            if fs and not (important and prefs["urgent_fullscreen"]):
                self.deferred = self.deferred or "fullscreen"
                continue
            items.append({"row": dict(r), "tier": tier})
        self.store.record(skip, "pulado", now)
        self.store.record([(i["row"]["key"], i["tier"], deadline(i["row"])) for i in items], "avisado", now)
        first = bool(sync and sync.get("first") and sync["result"] in ("ok", "parcial"))
        if items or first:
            self.alerts.emit({"items": items, "first": first, "fullscreen": fs, "now": now})

    def _arm(self):
        now, prefs = self.now(), self.store.prefs()
        cands = [now + MAX_SLEEP]
        if self.next_reminder:
            cands.append(self.next_reminder)
        if self.connected():
            t = at(now, prefs["auto_time"])
            cands.append(t if now < t and self.store.last_auto_day() != today(now) else at(now, prefs["auto_time"], 1))
        if self.deferred == "quiet":
            end = at(now, prefs["quiet_end"])
            cands.append(end if end > now else at(now, prefs["quiet_end"], 1))
        elif self.deferred == "fullscreen":
            cands.append(now + FS_RETRY)
        self.timer.start(int(max(5.0, min(cands) - now) * 1000))
