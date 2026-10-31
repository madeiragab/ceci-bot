"""Corrente de provedores de IA com um servidor HTTP falso local (nenhuma chave real, nenhum serviço de verdade).

Uso: python tests/chain_test.py
"""
import os
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["CECI_CONFIG_DIR"] = tempfile.mkdtemp(prefix="cecibot_chain_")  # nunca as chaves do usuário
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json  # noqa: E402
import threading  # noqa: E402
import time  # noqa: E402
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer  # noqa: E402

from PySide6.QtCore import QCoreApplication, QEventLoop  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from ceci.ia import keys, make_provider  # noqa: E402
from ceci.ia.apis import Claude, OpenAICompat, wait_of  # noqa: E402
from ceci.ia.assistant import Assistant  # noqa: E402
from ceci.ia.chain import CHAIN, ChainProvider, build  # noqa: E402
from ceci.ia.chat import ChatWindow, KeysDialog  # noqa: E402
from ceci.ia.context import Conversation  # noqa: E402
from ceci.ia.provider import AIError, Prompt  # noqa: E402
from ceci.sala.store import Store  # noqa: E402
from ceci.settings import CONFIG_DIR, PATH as SETTINGS, Settings  # noqa: E402

qa = QApplication(sys.argv)
fails = []
TMP = os.environ["CECI_CONFIG_DIR"]
KEY_A, KEY_B, KEY_C = "sk-teste-aaaaaaaaaaaa", "gsk_teste_bbbbbbbbbbbb", "sk-ant-teste-cccccccc"


def check(name, cond):
    print(("ok   " if cond else "FALHA"), name)
    if not cond:
        fails.append(name)


# --- servidor falso: cada caminho tem uma fila de respostas (status, corpo, cabeçalhos, atraso) ---
script, seen = {}, []


def ok(text, finish="stop"):
    return 200, {"choices": [{"message": {"role": "assistant", "content": text}, "finish_reason": finish}]}, {}, 0


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        seen.append((self.path, {k.lower(): v for k, v in self.headers.items()}, body))
        q = script.get(self.path)
        status, data, headers, delay = q.pop(0) if q else ok("[feliz] padrão")
        time.sleep(delay)
        raw = data.encode() if isinstance(data, str) else json.dumps(data).encode()
        try:
            self.send_response(status)
            for k, v in headers.items():
                self.send_header(k, v)
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
        except OSError:
            pass  # cliente desistiu (timeout de propósito)


srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
BASE = f"http://127.0.0.1:{srv.server_port}"


def chain(per_try=10):
    a = OpenAICompat("svc_a", "A", BASE + "/a", "m1", {"max_tokens": 50})
    b = OpenAICompat("svc_b", "B", BASE + "/b", "m2")
    c = Claude("svc_c", "C", BASE + "/c", "m3")
    return ChainProvider([a, b, c], per_try=per_try)


def paths():
    return [p for p, _, _ in seen]


def reset(**queues):
    script.clear()
    seen.clear()
    script.update({"/" + k: v for k, v in queues.items()})


P = Prompt(system="SISTEMA", message="oi")

# 1. sem chave: fora da corrente, nenhum pedido sai
ch = chain()
reset()
avail, why = ch.is_available()
try:
    ch.send_message(P, 5)
    kind = None
except AIError as e:
    kind = e.kind
check("sem chave: corrente desligada com motivo, 'indisponivel', nenhum pedido",
      not avail and "Chaves" in why and kind == "indisponivel" and not seen)
check("sem chave: a Ceci diz que não tem IA", "provedor de IA" == ch.name)

# 2. chaves guardadas com DPAPI, nunca em texto puro
for s, k in (("svc_a", KEY_A), ("svc_b", KEY_B), ("svc_c", KEY_C)):
    keys.put(s, k)
raw = open(keys.PATH, "rb").read() if sys.platform == "win32" else b""
check("chaves: arquivo protegido sem a chave em texto puro e lidas de volta",
      (sys.platform != "win32" or (KEY_A.encode() not in raw and KEY_B[:10].encode() not in raw))
      and keys.get("svc_a") == KEY_A and keys.get("svc_c") == KEY_C)
check("chaves: nome dos serviços com chave", ch.name == "A, B ou C")

# 3. primeiro da fila responde; a chave só vai pro próprio serviço
reset(a=[ok("[feliz] oi do A")])
r = ch.send_message(P, 10)
hdr = seen[0][1]
check("ordem: o primeiro responde e diz quem foi", r.provider == "svc_a/m1" and r.text == "[feliz] oi do A"
      and paths() == ["/a"])
check("chave: só no cabeçalho do próprio serviço, nunca no corpo",
      hdr.get("authorization") == f"Bearer {KEY_A}" and KEY_A not in json.dumps(seen[0][2]))
check("formato OpenAI: system + mensagem, corpo do serviço", seen[0][2]["messages"][0] == {
    "role": "system", "content": "SISTEMA"} and seen[0][2]["messages"][-1]["content"] == "oi"
    and seen[0][2]["max_tokens"] == 50 and seen[0][2]["model"] == "m1")

# 4. limite: passa pro próximo e o primeiro fica pausado pelo tempo informado
reset(a=[(429, {"error": {"message": "Rate limit reached on requests per day (RPD)"}}, {"Retry-After": "120"}, 0)],
      b=[ok("[feliz] oi do B"), ok("[feliz] B de novo")])
r = ch.send_message(P, 10)
until, err = ch.paused["svc_a/m1"]
check("limite: o próximo responde", r.provider == "svc_b/m2" and paths() == ["/a", "/b"])
check("limite: pausado pelo Retry-After", err.kind == "limite" and 100 < until - ch.now() <= 120)
check("limite: chave do B só no B", seen[1][1].get("authorization") == f"Bearer {KEY_B}")
seen.clear()
r = ch.send_message(P, 10)
check("pausado: não recebe pedido à toa", paths() == ["/b"] and r.provider == "svc_b/m2")
ch.forget("svc_a")
reset(a=[ok("[feliz] A voltou")])
check("chave trocada: o serviço volta na hora", ch.send_message(P, 10).provider == "svc_a/m1")

# 5. falhas de cada tipo passam pro próximo
for status, body, kind, pause in ((401, {"error": {"message": "Incorrect API key provided: sk-proj-abcdef123456"}},
                                   "sessao", 6 * 3600),
                                  (404, {"error": {"message": "model not found"}}, "indisponivel", 3600),
                                  (500, "erro interno", "conexao", 60),
                                  (200, "isso não é json", "falha", 60),
                                  (200, {"choices": [{"message": {"content": ""}}]}, "vazia", 60)):
    ch.paused.clear()
    reset(a=[(status, body, {}, 0)], b=[ok("[neutra] B")])
    r = ch.send_message(P, 10)
    until, err = ch.paused.get("svc_a/m1", (0, AIError("falha")))
    check(f"{status} → '{kind}', pausa {pause} s e o próximo responde",
          r.provider == "svc_b/m2" and err.kind == kind and abs(until - ch.now() - pause) < 5)
check("erro do serviço: pedaço de chave na mensagem vira [chave]", "sk-proj" not in str(
    AIError("x", keys.scrub("Incorrect API key provided: sk-proj-abcdef123456"))))

# 6. tempo de espera informado de jeitos diferentes
check("espera: Groq 'try again in 7m12.5s'", wait_of({}, "Please try again in 7m12.5s.") == 432.5)
check("espera: Gemini retryDelay", wait_of({}, '{"retryDelay": "36s"}') == 36)
check("espera: sem crédito (OpenAI) = 3 h", wait_of({}, '{"code": "insufficient_quota"}') == 3 * 3600)
check("espera: limite por minuto sem prazo = padrão", wait_of({}, "too many requests") is None)

# 7. todos no limite: a Ceci conta que é limite e quando volta
ch.paused.clear()
lim = (429, {"error": {"message": "slow down"}}, {"Retry-After": "30"}, 0)
reset(a=[lim], b=[lim], c=[(429, {"error": {"message": "x"}}, {"Retry-After": "90"}, 0)])
try:
    ch.send_message(P, 10)
    e = None
except AIError as x:
    e = x
check("todos no limite: 'limite' com a espera do primeiro que volta", e and e.kind == "limite" and 20 <= e.wait <= 30)

# 8. troca de IA: a nova recebe a conversa inteira em markdown; a mesma IA recebe só as últimas
ch.paused.clear()
md = "**Usuário:** meu gato chama Biscoito\n\n**Ceci:** Anotado!"
hp = Prompt(system="SISTEMA", message="qual o nome dele?", history=[("user", "meu gato chama Biscoito"),
                                                                   ("ceci", "Anotado!")],
            transcript=md, last_provider="svc_a/m1")
reset(a=[ok("[neutra] Biscoito")])
ch.send_message(hp, 10)
msgs = seen[0][2]["messages"]
check("mesma IA: últimas mensagens, sem o markdown", len(msgs) == 4 and "CONVERSA ATÉ AGORA" not in msgs[0]["content"])
reset(a=[lim], b=[ok("[neutra] Biscoito")])
ch.send_message(hp, 10)
msgs = seen[1][2]["messages"]
check("outra IA assume: recebe a conversa em markdown no lugar das últimas",
      "CONVERSA ATÉ AGORA" in msgs[0]["content"] and md in msgs[0]["content"] and len(msgs) == 2
      and msgs[1]["content"] == "qual o nome dele?")

# 9. resposta cortada
ch.paused.clear()
reset(a=[ok("[feliz] metade", finish="length")])
check("resposta cortada: complete=False", ch.send_message(P, 10).complete is False)

# 10. formato Claude (Anthropic)
ch.paused.update({"svc_a/m1": (ch.now() + 999, AIError("limite")), "svc_b/m2": (ch.now() + 999, AIError("limite"))})
reset(c=[(200, {"content": [{"type": "text", "text": "[feliz] oi do Claude"}], "stop_reason": "end_turn"}, {}, 0)])
cp = Prompt(system="SISTEMA", message="e agora?", history=[("ceci", "começa com ela"), ("user", "a"), ("user", "b"),
                                                          ("ceci", "c")], last_provider="svc_c/m3")
r = ch.send_message(cp, 10)
_, h, body = seen[0]
check("Claude: x-api-key e anthropic-version, sem Authorization",
      h.get("x-api-key") == KEY_C and h.get("anthropic-version") == "2023-06-01" and "authorization" not in h)
check("Claude: system separado, papéis alternados começando pelo usuário",
      body["system"] == "SISTEMA" and [m["role"] for m in body["messages"]] == ["user", "assistant", "user"]
      and body["messages"][0]["content"] == "a\n\nb" and r.text == "[feliz] oi do Claude")
reset(c=[(200, {"content": [{"type": "text", "text": "[feliz] meia"}], "stop_reason": "max_tokens"}, {}, 0)])
check("Claude: max_tokens = resposta cortada", ch.send_message(cp, 10).complete is False)

# 11. serviço travado não come o tempo dos outros; cancelar
ch = chain(per_try=0.5)
reset(a=[(200, {}, {}, 2)], b=[ok("[feliz] rápido")])
t = time.monotonic()
r = ch.send_message(P, 10)
check("travado: desiste em 0,5 s e o próximo responde", r.provider == "svc_b/m2" and time.monotonic() - t < 1.8
      and ch.paused["svc_a/m1"][1].kind == "timeout")
ch = chain()
reset(a=[(200, ok("[feliz] tarde")[1], {}, 1)])
threading.Timer(0.2, ch.cancel).start()
try:
    ch.send_message(P, 10)
    kind = None
except AIError as e:
    kind = e.kind
check("cancelar: a resposta que chega depois é descartada", kind == "cancelada")
time.sleep(1)


# 12. na Ceci: histórico local, quem respondeu, troca com o markdown
class S(dict):
    def save(self):
        pass


def wait(cond, ms=8000):
    end = time.monotonic() + ms / 1000
    while not cond() and time.monotonic() < end:
        QCoreApplication.processEvents(QEventLoop.AllEvents, 50)
        time.sleep(0.01)
    return cond()


ch = chain()
conv = Conversation(os.path.join(TMP, "conversa.json"))
ai = Assistant(ch, Store(os.path.join(TMP, "sala.db")), S(ai_academic=None), conv=conv,
               personality=type("P", (), {"key": ("p", 1, 1), "instructions": lambda self: "PERSONALIDADE"})())
got = []
ai.answered.connect(got.append)
ai.failed.connect(got.append)
reset(a=[ok("[feliz] Oi! Tudo ótimo."), lim], b=[ok("[curiosa] Biscoito, laranja."), ok("[feliz] De nada!")])
ai.handle("oi ceci")
wait(lambda: got)
ai.handle("meu gato chama Biscoito, é laranja. qual o nome dele?")
wait(lambda: len(got) >= 2)
sysmsg = seen[-1][2]["messages"][0]["content"]
check("Ceci: a primeira resposta vem do A e fica no histórico local com quem respondeu",
      got[0].get("mood") == "feliz" and conv.messages[1].get("provider") == "svc_a/m1")
check("Ceci: A no limite → B assume com a conversa em markdown",
      conv.state["provider"] == "svc_b/m2" and "**Usuário:** oi ceci" in sysmsg and "**Ceci:** Oi! Tudo ótimo." in sysmsg
      and "PERSONALIDADE" in sysmsg and got[1].get("mood") == "curiosa")
saved = json.load(open(conv.path, encoding="utf8"))
check("Ceci: histórico salvo no PC (conversa.json) com o provedor de cada resposta",
      [m.get("provider") for m in saved["messages"] if m["role"] == "ceci"] == ["svc_a/m1", "svc_b/m2"])
ai.handle("valeu")
wait(lambda: len(got) >= 3)
check("Ceci: mesma IA de novo → só as últimas mensagens, sem repetir o markdown",
      "CONVERSA ATÉ AGORA" not in seen[-1][2]["messages"][0]["content"] and len(seen[-1][2]["messages"]) > 2)
check("Ceci: nenhuma chave no histórico salvo", not any(k in open(conv.path, encoding="utf8").read()
                                                         for k in (KEY_A, KEY_B, KEY_C)))
win = ChatWindow(ai, ai.handle)
check("chat: mostra a corrente (pausado/pronto) e quem respondeu",
      "pausado" in win.status.text() and "pronto" in win.status.text() and "svc_b/m2" in win.view.toHtml())

# 13. janela de chaves: salva protegida, nunca mostra a chave
dlg = KeysDialog(ch)
f, b = dlg.fields["groq"]
f.setText("  gsk_da_janela_123456  ")
dlg._save()
check("janela de chaves: salva (sem espaços) e o serviço volta a ser tentado", keys.get("groq") == "gsk_da_janela_123456")
dlg = KeysDialog(ch)
f, b = dlg.fields["groq"]
check("janela de chaves: campo vazio e escondido, só avisa que está salva",
      f.text() == "" and "salva" in f.placeholderText() and f.echoMode() == f.EchoMode.Password and b.isEnabled())
dlg._drop("groq")
check("janela de chaves: Apagar remove", keys.get("groq") is None)

# 14. configuração
with open(SETTINGS, "w", encoding="utf8") as fh:
    json.dump({"ai_provider": "gemini_web"}, fh)
check("settings antigo (gemini_web, bloqueado) passa pra corrente", Settings()["ai_provider"] == "corrente")
check("ordem padrão: GPT → Claude → OmniRoute → grátis por dia",
      [s for s, _, _ in CHAIN][:5] == ["openai", "anthropic", "omniroute", "gemini", "groq"])
custom = build(["groq/openai/gpt-oss-20b", "inexistente/x"])
check("ai_chain troca a ordem (e ignora serviço desconhecido)",
      [p.id for p in custom] == ["groq/openai/gpt-oss-20b"] and custom[0].extra.get("reasoning_effort") == "low")
check("make_provider: corrente com todos os serviços", isinstance(make_provider("corrente"), ChainProvider)
      and len(make_provider("corrente").entries) == len(CHAIN))
check("chaves fora do projeto (pasta de configuração)", os.path.dirname(keys.PATH) == CONFIG_DIR)

srv.shutdown()
print("\n" + ("TUDO OK" if not fails else f"{len(fails)} FALHA(S): {fails}"))
sys.exit(1 if fails else 0)
