"""Fase 2 — Sala Virtual com dados fictícios (servidor Moodle de mentira em 127.0.0.1; nenhuma conta real).

Cobre os 18 cenários obrigatórios e mais: sessão protegida pelo Windows, horário silencioso, logs sem segredos e
as janelas abrindo. Uso: python tests/sala_test.py
"""
import os
import sys
import tempfile
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["CECI_CONFIG_DIR"] = TMP = tempfile.mkdtemp(prefix="cecibot_sala_")  # nunca as do usuário
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtCore import QCoreApplication, QEventLoop, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from ceci.sala import protect  # noqa: E402
from ceci.sala.clock import at  # noqa: E402
from ceci.sala.reminders import due_now, schedule  # noqa: E402
from ceci.sala.service import LOG, SalaVirtual  # noqa: E402
from ceci.sala.store import Store, status  # noqa: E402
from fake_moodle import PASSWORD, SESSION, SESSKEY, TOKEN, USER, Fake, serve  # noqa: E402

qa = QApplication(sys.argv)
fails = []
DAY = 86400


def check(name, cond):
    print(("ok   " if cond else "FALHA"), name)
    if not cond:
        fails.append(name)


class MemSession:
    def __init__(self, data):
        self.data = data

    def load(self):
        return self.data

    def save(self, d):
        self.data = d

    def clear(self):
        self.data = None


class TimerStub:  # o timer real dispararia consultas no meio do teste (relógio falso)
    ms = None

    def start(self, ms):
        self.ms = ms

    def stop(self):
        self.ms = None


T0 = time.time()
T = [T0]
fake = Fake(T0)
srv = serve(fake)
store = Store(os.path.join(TMP, "sala.db"))
store.set_prefs(url=fake.base, quiet=False)
cookie = {"name": "MoodleSession", "value": SESSION, "domain": "127.0.0.1", "path": "/"}
sess = MemSession({"base": fake.base, "cookies": [cookie], "ua": "teste", "ical": None})
sala = SalaVirtual(store=store, clock=lambda: T[0], session=sess, startup_delay=0)
sala.timer = TimerStub()
alerts = []
sala.alerts.connect(alerts.append)


def run_sync(trigger="manual", who=sala):
    got = {}
    loop = QEventLoop()

    def fin(o):
        got.update(o)
        loop.quit()
    who.finished.connect(fin)
    if who.sync(trigger) and not got:
        QTimer.singleShot(60000, loop.quit)
        loop.exec()
    who.finished.disconnect(fin)
    QCoreApplication.processEvents()
    return got


def rows():
    return {r["key"]: dict(r) for r in store.rows()}


def fired(items, key, tier=None):
    return any(r["key"] == key and (tier is None or t == tier) for r, t in items)


# 1. primeira sincronização ------------------------------------------------------------------------------
out = run_sync()
R = rows()
check("1 primeira sincronização termina ok", out.get("result") == "ok" and out.get("first"))
check("1 todas as disciplinas registradas (inclusive a passada)", {c["id"] for c in store.courses()} == {101, 102, 103, 90})
check("1 atividades com prazo/entrega guardadas; recurso e fórum sem prazo ficam de fora",
      set(R) == {"cm:501", "cm:502", "cm:503", "cm:504", "cm:505", "ev:9001"})
check("1 tipos certos (envio, questionário, fórum, evento)",
      (R["cm:501"]["kind"], R["cm:502"]["kind"], R["cm:505"]["kind"], R["ev:9001"]["kind"])
      == ("envio", "questionario", "forum", "evento"))
check("1 prazo exato do calendário e link direto", R["cm:501"]["due"] == int(fake.acts[501]["due"])
      and R["cm:501"]["url"].endswith("/mod/assign/view.php?id=501"))
check("1 primeira consulta não dispara 'atividade nova' (vira resumo)",
      not [c for c in out["changes"] if c["kind"] == "nova"] and alerts and alerts[-1]["first"])
# 9. disciplina sem atividades
check("9 disciplina sem atividades: lida sem erro", 103 not in out["failed"] and out["result"] == "ok")
# 13. duplicatas
check("13 sem duplicatas: questionário visto em 4 fontes = 1 registro",
      sum(1 for r in R.values() if r["cmid"] == 502) == 1
      and set(R["cm:502"]["sources"].split(",")) == {"calendario", "disciplina", "linha_do_tempo", "pagina"})
# 6. rascunho
check("6 rascunho salvo NÃO é entrega", R["cm:503"]["sub"] == "rascunho" and status(R["cm:503"], T0) == "pendente")
# 7. sem data
check("7 atividade sem data: sem prazo inventado e sem lembrete",
      R["cm:504"]["due"] is None and status(R["cm:504"], T0) == "sem_prazo" and schedule(R["cm:504"], store.prefs()) == [])

# 2. atividade nova --------------------------------------------------------------------------------------
fake.acts[508] = {"course": 101, "mod": "assign", "name": "Trabalho final", "due": T0 + 20 * DAY, "status": "new"}
alerts.clear()
out = run_sync()
check("2 atividade nova detectada", any(c["kind"] == "nova" and c["key"] == "cm:508" for c in out["changes"]))
check("2 aviso de atividade nova", any(i["tier"] == "nova" and i["row"]["key"] == "cm:508"
                                       for a in alerts for i in a["items"]))

# 3. prazo alterado --------------------------------------------------------------------------------------
old = rows()["cm:503"]["due"]
fake.acts[503]["due"] = T0 + 9 * DAY
alerts.clear()
out = run_sync()
ch = [c for c in out["changes"] if c["kind"] == "prazo" and c["key"] == "cm:503"]
check("3 prazo alterado vai para o histórico (antes/depois)", ch and abs(ch[0]["before"] - old) < 1
      and abs(ch[0]["after"] - fake.acts[503]["due"]) < 1)
check("3 aviso de prazo alterado", any(i["tier"] == "prazo_alterado" for a in alerts for i in a["items"]))
f, _, _ = due_now(store.rows(), store.prefs(), fake.acts[503]["due"] - 7 * DAY + 60, store.sent())
check("3 lembretes recalculados pelo prazo novo", fired(f, "cm:503", "7d"))

# 5. entrega confirmada ----------------------------------------------------------------------------------
fake.acts[501]["status"] = "submitted"
out = run_sync()
check("5 entrega confirmada pelo Moodle", any(c["kind"] == "entregue" and c["key"] == "cm:501" for c in out["changes"])
      and status(rows()["cm:501"], T0) == "entregue")
f, _, _ = due_now(store.rows(), store.prefs(), fake.acts[501]["due"] - 3600, store.sent())
check("5 entregue não recebe mais lembrete", not fired(f, "cm:501"))

# 12. sincronização parcial ------------------------------------------------------------------------------
fake.fail_course = {102}
out = run_sync()
check("12 disciplina que falhou deixa o resultado parcial", out["result"] == "parcial" and 102 in out["failed"]
      and "1 de 3" in out["message"])
check("12 dados antigos da disciplina que falhou continuam (não viram indisponíveis)",
      rows()["cm:504"]["state"] == "ativa" and rows()["cm:504"]["name"] == "Relatório sem data")
fake.fail_course = set()

# 8. removida / inacessível ------------------------------------------------------------------------------
fake.gone.add(505)
n_before = len(rows())
out = run_sync()
check("8 atividade removida: investigada e marcada indisponível", rows()["cm:505"]["state"] == "indisponivel"
      and any(c["kind"] == "indisponivel" and c["key"] == "cm:505" for c in out["changes"]))
check("8 nada é apagado do banco", len(rows()) == n_before)

# 10. falha de rede --------------------------------------------------------------------------------------
snap = rows()
store.set_prefs(url="http://sala-virtual.invalid")
out = run_sync()
check("10 sem internet: falha clara, sem afirmar sucesso", out["result"] == "falhou" and out["kind"] == "sem_internet")
store.set_prefs(url=fake.base)
fake.down = True
out = run_sync()
check("10 servidor fora do ar: falha clara", out["result"] == "falhou" and out["kind"] == "servidor")
fake.down = False
check("10 falha não mexe nos dados salvos", rows() == snap)

# 11. sessão expirada ------------------------------------------------------------------------------------
fake.valid = set()
out = run_sync()
check("11 sessão expirada detectada", out["result"] == "falhou" and out["kind"] == "sessao" and sala.session_expired())
sess.data["ical"] = f"{fake.base}/calendar/export_execute.php?userid=2&authtoken={TOKEN}"
fake.acts[502]["close"] += DAY
fake.ical_extra = [{"id": 7777, "name": "Seminário de PO", "timestart": int(T0 + 5 * DAY), "course": {"id": 101}}]
out = run_sync()
check("11 sessão expirada + calendário exportado: só prazos, marcado como parcial",
      out["result"] == "parcial" and out["kind"] == "sessao" and "não foi conferido" in out["message"])
check("11 prazo novo pelo calendário exportado",
      any(c["kind"] == "prazo" and c["key"] == "cm:502" for c in out["changes"])
      and rows()["cm:502"]["close"] == int(fake.acts[502]["close"]))
check("11 evento novo só do calendário também aparece", "ev:7777" in rows())
fake.valid = {SESSION}

# 4. atividade vencida -----------------------------------------------------------------------------------
T[0] = fake.acts[503]["due"] + 3600
out = run_sync()
check("4 vencida sem envio = atrasada", status(rows()["cm:503"], T[0]) == "atrasada"
      and any(c["kind"] == "atrasada" and c["key"] == "cm:503" for c in out["changes"]))
f, _, _ = due_now(store.rows(), store.prefs(), T[0], store.sent())
check("4 lembrete de atraso", fired(f, "cm:503", "atrasada") or (("cm:503", "atrasada", rows()["cm:503"]["due"])
                                                                   in store.sent()))
T[0] = T0

# 14. sem notificações repetidas -------------------------------------------------------------------------
T[0] = fake.acts[508]["due"] - 3 * DAY + 60
alerts.clear()
sala._remind()
first_round = [i["row"]["key"] + i["tier"] for a in alerts for i in a["items"]]
sala._remind()
second = [i["row"]["key"] + i["tier"] for a in alerts for i in a["items"]][len(first_round):]
check("14 lembrete sai uma vez", "cm:5083d" in first_round and not second)

# 17. lembretes offline ----------------------------------------------------------------------------------
fake.down = True
n = fake.requests
T[0] = fake.acts[508]["due"] - 24 * 3600 + 60
alerts.clear()
sala._remind()
check("17 lembrete calculado offline, sem tocar no Moodle",
      any(i["row"]["key"] == "cm:508" and i["tier"] == "24h" for a in alerts for i in a["items"]) and fake.requests == n)
fake.down = False

# horário silencioso
store.set_prefs(quiet=True, quiet_start="22:00", quiet_end="07:00")
fake.acts[509] = {"course": 102, "mod": "assign", "name": "Lista extra", "due": T0 + 30 * DAY, "status": "new"}
T[0] = T0
run_sync()
tq = at(fake.acts[509]["due"] - 2.5 * DAY, "23:00")
T[0] = tq
alerts.clear()
sala._remind()
check("horário silencioso segura o lembrete comum", not any(i["row"]["key"] == "cm:509" for a in alerts for i in a["items"])
      and sala.deferred == "quiet")
T[0] = at(tq, "07:30", 1)
sala._remind()
check("... e ele sai quando o silêncio acaba", any(i["row"]["key"] == "cm:509" and i["tier"] == "3d"
                                                  for a in alerts for i in a["items"]))
store.set_prefs(quiet=False)

# 15. uma tentativa automática por dia -------------------------------------------------------------------
T[0] = at(T0, "07:00", 5)
check("15 antes do horário: nada automático", not sala.auto_due())
T[0] = at(T0, "08:05", 5)
check("15 depois do horário: consulta do dia pendente", sala.auto_due())
store.set_prefs(url="http://sala-virtual.invalid")
out = run_sync("auto")
check("15 tentativa automática falhou...", out["result"] == "falhou" and out["trigger"] == "auto")
check("15 ... e não tenta de novo sozinha no mesmo dia", not sala.auto_due() and sala.busy is None)
check("15 próximo despertar agendado (sem polling)", sala.timer.ms and sala.timer.ms >= 5000)
store.set_prefs(url=fake.base)
T[0] = at(T0, "08:05", 6)
check("15 dia seguinte: nova tentativa liberada", sala.auto_due())
# app aberto depois do horário: faz a consulta pendente ao iniciar
T[0] = at(T0, "10:00", 6)
s2 = SalaVirtual(store=store, clock=lambda: T[0], session=sess, startup_delay=0)
s2.timer = TimerStub()
got = {}
loop = QEventLoop()
s2.finished.connect(lambda o: (got.update(o), loop.quit()))
s2.start()
QTimer.singleShot(60000, loop.quit)
loop.exec()
check("15 abriu depois das 08:00: consulta pendente roda ao iniciar", got.get("trigger") == "auto"
      and got.get("result") == "ok" and not s2.auto_due())

# 16. consulta manual ------------------------------------------------------------------------------------
T[0] = at(T0, "07:30", 7)
out = run_sync("manual")
T[0] = at(T0, "08:01", 7)
check("16 consulta manual não gasta a automática do dia", out["result"] == "ok" and sala.auto_due())
T[0] = T0

# 18. navegador encerrado depois do login ----------------------------------------------------------------
try:
    import psutil
    from ceci.sala.login import login

    def fill(page):  # credenciais falsas, no servidor falso local
        page.fill("#username", USER)
        page.fill("#password", PASSWORD)
        page.click("#loginbtn")

    fake.valid = {SESSION}
    got = login(fake.base, headless=True, on_page=fill, timeout=60)
    check("18 login (falso) devolve só os cookies da sessão", [c["name"] for c in got["cookies"]] == ["MoodleSession"])
    time.sleep(1.5)
    left = []
    for p in psutil.process_iter(["name", "cmdline"]):
        try:
            cmd = " ".join(p.info["cmdline"] or []).lower()
        except (psutil.Error, TypeError):
            continue
        if "playwright" in cmd or "ms-playwright" in cmd:
            left.append(p.info["name"])
    check("18 nenhum processo do navegador/Playwright fica aberto", not left)
except ImportError as e:
    print("PULADO 18 (", e, ")")

# sessão protegida pelo Windows
protect.save({"cookies": [{"name": "MoodleSession", "value": "valor-secreto-123"}]})
raw = open(protect.PATH, "rb").read()
check("sessão salva cifrada (DPAPI): o arquivo não tem o cookie em texto", b"valor-secreto-123" not in raw
      if sys.platform == "win32" else True)
check("... e abre de volta", protect.load()["cookies"][0]["value"] == "valor-secreto-123")
protect.clear()
check("... desconectar apaga", protect.load() is None and not os.path.exists(protect.PATH))

# logs sem segredos
log = open(LOG, encoding="utf8").read() if os.path.exists(LOG) else ""
check("log sem sesskey, cookie nem token", log and not any(s in log for s in (SESSKEY, SESSION, TOKEN, PASSWORD)))

# o que ela fala quando você pergunta (menu ou caixinha), com os dados salvos
from ceci.ia.router import route  # noqa: E402
from ceci.sala import texts  # noqa: E402
from ceci.sala.ui import SalaDialog  # noqa: E402
said = texts.answer(store, "atividades", T0)
todo = [r for r in store.rows() if status(r, T0) == "pendente" and r["due"]]
check("\"atividades\" diz quantas e fala nome, disciplina e prazo de cada uma", said[0].startswith("Tem ") and todo
      and any(todo[0]["name"] in t and "faltam" in t for t in said))
check("\"resumo\" fala hoje, semana e atrasadas", said and texts.answer(store, "resumo", T0)[0].startswith("Hoje vence"))
check("sem nenhuma consulta ela diz que ainda não conferiu",
      texts.answer(Store(os.path.join(tempfile.mkdtemp(), "v.db")), "atividades", T0)[0].startswith("Ainda não conferi"))
check("caixinha: comandos registrados viram ação local; perguntas e conversa não",
      [tuple(route(t)[:2]) for t in ("atividades", "o que vence hoje?", "atrasadas", "próxima entrega", "resumo",
                                     "conferir", "fiz lista 3", "não fiz lista 3", "qual a capital da frança")]
      == [("local", "atividades"), ("academico", ""), ("local", "atrasadas"), ("local", "prazo"),
          ("local", "resumo"), ("local", "conferir"), ("local", "fiz"), ("local", "desfazer"), ("conversa", "")])
check("\"fiz\" acha a atividade pelo pedaço do nome, sem acento",
      [r["key"] for r in texts.find(store, texts.norm(todo[0]["name"]).upper(), T0)] == [todo[0]["key"]])
SalaDialog(sala).show()
QCoreApplication.processEvents()

srv.shutdown()
print(f"\n{len(fails)} falha(s)" if fails else "\ntudo ok")
sys.exit(1 if fails else 0)
