"""Fase 3: núcleo de IA da Ceci com um provedor falso (nenhuma IA de verdade, nenhuma conta real).

Moodle falso local para os dados da Sala Virtual. Uso: python tests/ia_test.py
"""
import os
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["CECI_CONFIG_DIR"] = tempfile.mkdtemp(prefix="cecibot_ia_")  # nunca as do usuário
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import json  # noqa: E402
import threading  # noqa: E402
import time  # noqa: E402

from PySide6.QtCore import QCoreApplication, QEventLoop, Qt, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import main as M  # noqa: E402
M.fullscreen_app_active = lambda: False  # tela cheia de verdade no PC não entra no teste
from ceci.command import CommandBox  # noqa: E402
from ceci.ia import academic, prompts  # noqa: E402
from ceci.ia.chat import ChatWindow  # noqa: E402
from ceci.ia.context import Conversation  # noqa: E402
from ceci.ia.gemini_web import GeminiWebProvider  # noqa: E402
from ceci.ia.personality import Personality  # noqa: E402
from ceci.ia.provider import AIError, AIProvider, Reply  # noqa: E402
from ceci.ia.router import route  # noqa: E402
from ceci.sala import protect  # noqa: E402
from ceci.sala.store import Store  # noqa: E402
from fake_moodle import SESSION, SESSKEY, TOKEN, Fake, serve  # noqa: E402

qa = QApplication(sys.argv)
fails = []


def check(name, cond):
    print(("ok   " if cond else "FALHA"), name)
    if not cond:
        fails.append(name)


class FakeProvider(AIProvider):
    """Respostas roteirizadas; `delay` segura a resposta (para testar espera e cancelamento)."""
    name = "IA de teste"

    def __init__(self):
        self.calls, self.script, self.available, self.delay, self.resets = [], [], True, 0.0, 0
        self.stop = threading.Event()

    def is_available(self):
        return self.available, "desligada no teste"

    def send_message(self, prompt, timeout):
        self.calls.append(prompt)
        self.stop.clear()
        step = self.script.pop(0) if self.script else "[feliz] Opa!"
        if self.stop.wait(self.delay):
            raise AIError("cancelada")
        if isinstance(step, AIError):
            raise step
        return step if isinstance(step, Reply) else Reply(step, session_id="conversa-1")

    def reset_session(self):
        self.resets += 1

    def cancel(self):
        self.stop.set()


def wait(cond, ms=8000):
    end = time.monotonic() + ms / 1000
    while not cond() and time.monotonic() < end:
        QCoreApplication.processEvents(QEventLoop.AllEvents, 50)
        time.sleep(0.01)
    return cond()


# --- app com dados reais de um Moodle falso ---
fake = Fake(time.time())
fake.acts[530] = {"course": 101, "mod": "assign", "name": "Lista 9 (amanhã)", "due": time.time() + 20 * 3600,
                  "status": "new"}
srv = serve(fake)
protect.save({"base": fake.base, "cookies": [{"name": "MoodleSession", "value": SESSION, "domain": "127.0.0.1",
                                              "path": "/"}], "ua": "teste", "ical": None})
app = M.App(qa)
app.s["follow_mouse"] = False
app.sala.store.set_prefs(url=fake.base, quiet=False)
w = app.win
w.set_start_pos()
w.show()
w.play("idle", force=True)
loop = QEventLoop()
app.sala.finished.connect(loop.quit)
app.sala.sync("manual")
QTimer.singleShot(60000, loop.quit)
loop.exec()
check("Sala Virtual sincronizada (dados para as perguntas)", len(app.sala.store.rows()) >= 5)

prov = FakeProvider()
app.ai.provider = prov
played, said = [], []
orig_play = w.play
w.play = lambda aid, **kw: (played.append(aid), orig_play(aid, **kw))[1]
orig_many = app.speech.say_many
app.speech.say_many = lambda lines, cat="sv_info": (said.extend(lines), orig_many(lines, cat))[1]


def send(text, done=None):
    played.clear()
    said.clear()
    n = len(app.ai.conv.messages)
    app.command(text)
    if done is None:
        done = lambda: app.ai.busy is None and len(app.ai.conv.messages) > n + 1  # noqa: E731
    return wait(done)


# 1, 2, 6. conversa simples, com a personalidade, sem histórico anterior
prov.script = ["[rindo] Opa! Tudo certo por aqui. E aí?"]
send("Oi, Ceci, tudo bem?")
p = prov.calls[-1]
check("1. conversa simples vai para a IA e a resposta sai no balão", len(prov.calls) == 1 and
      said == ["Opa! Tudo certo por aqui. E aí?"])
check("2. personalidade do ceci_personality.txt + regras do app (sem romance) no envio",
      "Corvinal" in p.system and "Ozzy e Bowie" in p.system and "Nada de comportamento romântico" in p.system)
check("6. primeira conversa: sem histórico e com sessão nova (a personalidade vai junto)",
      p.history == [] and p.new_session and p.session_id is None)
check("resposta da IA vira animação pelo humor ([rindo] → Feliz) depois de Observando",
      played[:1] == ["observando"] and played[-1] == "feliz")
check("mensagem e resposta ficam no histórico", [m["role"] for m in app.ai.conv.messages[-2:]] == ["user", "ceci"])

prov.script = ["Pera... recursividade é uma função que chama ela mesma."]
send("me explica recursividade")
check("continua a mesma conversa: histórico curto e sessão do provedor", prov.calls[-1].history and
      not prov.calls[-1].new_session and prov.calls[-1].session_id == "conversa-1")
check("sem etiqueta de humor: animação adivinhada pelo texto (\"Pera\" → Curiosa)", played[-1] == "curiosa")

# 3. comando local sem IA
n = len(prov.calls)
send("Mostra minhas atividades.", done=lambda: bool(said))
check("3. comando local não consulta a IA e ela fala as atividades", len(prov.calls) == n and said
      and said[0].startswith("Tem "))
send("abre o chat", done=lambda: app.chat_win is not None)
check("\"abre o chat\" abre o histórico (comando local)", app.chat_win.isVisible() and len(prov.calls) == n)

# 4. pergunta acadêmica: pede permissão uma vez, depois manda só o recorte
send("Tenho alguma atividade pra amanhã?", done=lambda: bool(said))
check("4a. dados acadêmicos só com autorização: ela pergunta antes", len(prov.calls) == n
      and app.ai.consent_pending and "Posso?" in said[0])
prov.script = ["[preocupada] Tem sim: Lista 9, amanhã. Não deixa pra última hora."]
send("sim")
p = prov.calls[-1]
data = json.loads(p.message.split("<dados_sala_virtual>")[1].split("</dados_sala_virtual>")[0])
check("4b. depois do \"sim\": pergunta + contexto estruturado da Sala Virtual", "PERGUNTA:" in p.message
      and "Tenho alguma atividade pra amanhã?" in p.message and data["modulo"] == "sala_virtual"
      and data["ultima_sincronizacao"] and data["sincronizacao_completa"])
check("4c. só o recorte de amanhã (não o banco inteiro)", [a["titulo"] for a in data["atividades"]]
      == ["Lista 9 (amanhã)"] and len(app.sala.store.rows()) > 3)
check("4d. nada de cookie, sesskey ou token no que vai para a IA",
      not any(s in p.message + p.system for s in (SESSION, SESSKEY, TOKEN)))
check("4e. prazo em menos de 24 h → animação Prazo urgente", played[-1] == "prazo")
check("permissão fica salva", app.s["ai_academic"] is True)

# 5. pergunta de acompanhamento
prov.script = ["[explicando] Você tem 3 essa semana."]
send("Quais atividades tenho essa semana?")
first = list(app.ai.conv.state["last_keys"])
prov.script = ["[neutra] A primeira é a Lista 9."]
send("E qual delas vence primeiro?")
data2 = json.loads(prov.calls[-1].message.split("<dados_sala_virtual>")[1].split("</dados_sala_virtual>")[0])
check("5. acompanhamento usa o mesmo conjunto de atividades da resposta anterior",
      first and data2["filtro"] == "seguimento da pergunta anterior"
      and len(data2["atividades"]) == len(first))
check("atividade encontrada → animação Mostrando tarefa (ou Prazo urgente)", played[-1] in ("tarefa", "prazo"))

# 9. falha de conexão: mensagem guardada, "tenta de novo" reenvia uma vez só
prov.script = [AIError("conexao", "caiu")]
send("conta uma piada")
check("9a. falha de conexão: ela avisa (sem inventar resposta) e anima Erro", said and "conexão" in said[0]
      and played[-1] == "erro" and app.ai.retry_text == "conta uma piada")
prov.script = ["[rindo] Por que o programador foi pro mato? Pra pegar um bug. KKKKK"]
n = len(prov.calls)
send("tenta de novo")
check("9b. \"tenta de novo\" manda a mesma mensagem, uma vez", len(prov.calls) == n + 1
      and prov.calls[-1].message == "conta uma piada" and "bug" in said[0])

# 12. cancelamento + envio duplicado
prov.delay = 3.0
prov.script = ["[neutra] resposta atrasada"]
played.clear()
n = len(prov.calls)
app.command("me fala de banco de dados relacional")
check("12a. esperando a IA: Pensando/Processando sem travar a tela",
      wait(lambda: "pensando" in played, 3000) and app.ai.busy)
app.command("me fala de banco de dados relacional")  # mesma mensagem de novo
check("envio duplicado é ignorado", wait(lambda: len(prov.calls) == n + 1, 1000) and len(prov.calls) == n + 1)
said.clear()
app.command("para")
check("12b. \"para\" cancela: ela avisa e a resposta atrasada é descartada", app.ai.busy is None
      and said and "deixei essa pra lá" in said[0])
time.sleep(0.3)
wait(lambda: False, 600)
check("12c. nada da resposta cancelada aparece depois", not any("atrasada" in t for t in said))
prov.delay = 0.0

# incompleta + vazia
prov.script = [AIError("incompleta", partial="[explicando] Um banco relacional guarda tabelas e")]
send("e um banco relacional?")
check("resposta cortada: mostra o que veio e avisa", said and said[0].startswith("Um banco relacional")
      and "cortada" in said[-1] and app.ai.conv.messages[-1]["complete"] is False)
prov.script = ["   "]
send("oi de novo")
check("resposta vazia: ela diz que veio vazia", said and "nada" in said[0])

# 8. sessão reiniciada
send("nova conversa", done=lambda: bool(said))
prov.script = ["[feliz] Opa!"]
send("oi")
check("8. nova conversa: provedor esquece, personalidade vai de novo, sem histórico antigo",
      prov.resets == 1 and prov.calls[-1].new_session and prov.calls[-1].history == [])

# personalidade atualizada sem reescrever o app
tmp = os.path.join(tempfile.mkdtemp(), "ceci_personality.txt")
open(tmp, "w", encoding="utf8").write("Você é Ceci. Versão 1.")
app.ai.persona = Personality((tmp,))
send("oi")
time.sleep(0.05)
open(tmp, "w", encoding="utf8").write("Você é Ceci. Versão 2, mais longa.")
send("e agora?")
check("arquivo de personalidade mudou: relido e reaplicado (sessão nova) sem reiniciar o app",
      "Versão 2" in prov.calls[-1].system and prov.calls[-1].new_session)
app.ai.persona = Personality()

# 10, 11. dados acadêmicos: sem sincronização / desatualizados
empty = Store(os.path.join(tempfile.mkdtemp(), "vazio.db"))
ctx, keys = academic.build(empty, "tenho atividade amanha", time.time())
check("10. sem dados da Sala Virtual: contexto diz que não há dados (e lista vazia)",
      ctx["atividades"] == [] and "aviso" in ctx and ctx["ultima_sincronizacao"] is None)
ctx, _ = academic.build(app.sala.store, "quais atividades tenho", time.time() + 30 * 3600)
check("11. dados com mais de 26 h: marcados como desatualizados", ctx["desatualizado"] is True)

# sem IA: comandos e perguntas acadêmicas continuam funcionando
app.ai.provider = GeminiWebProvider()
check("Gemini Web: indisponível, com o motivo documentado (robots.txt + Termos do Google)",
      GeminiWebProvider().is_available() == (False, GeminiWebProvider().is_available()[1])
      and "robots.txt" in GeminiWebProvider().is_available()[1])
send("Tenho alguma atividade pra amanhã?", done=lambda: bool(said))
check("sem IA: pergunta acadêmica responde com os dados locais", said and "vencendo amanhã" in said[0])
send("conta uma piada", done=lambda: bool(said))
check("sem IA: conversa diz honestamente que não tem IA conectada", said and "não tenho uma IA" in said[0])
app.ai.provider = prov

# 7. histórico: fecha, reabre e continua lá (inclusive depois de reiniciar)
app.chat_win.close()
app.open_chat()
QCoreApplication.processEvents()
html = app.chat_win.view.toPlainText()
check("7. reabrir o chat mostra a conversa inteira (fechar não apaga)", "Por que o programador" in html
      and "Lista 9" in html)
again = Conversation()
check("histórico salvo no disco: outra instância lê as mesmas mensagens",
      len(again.messages) == len(app.ai.conv.messages))
chat2 = ChatWindow(app.ai, app.command)
chat2.input.setText("oi pelo chat")
prov.script = ["[feliz] Oi pelo chat também!"]
n = len(prov.calls)
chat2._send()
check("a janela do chat manda para a mesma conversa", wait(lambda: len(prov.calls) == n + 1)
      and prov.calls[-1].message == "oi pelo chat")
wait(lambda: app.ai.busy is None)

# 13. interface da caixinha preservada
box = CommandBox()
check("13. caixinha igual: sem moldura, transparente, 260 px, mesmo texto",
      bool(box.windowFlags() & Qt.FramelessWindowHint) and box.testAttribute(Qt.WA_TranslucentBackground)
      and box.width() == 260 and box.placeholderText() == "fala comigo…")

# roteador: comandos registrados x conversa x dados
check("roteador: exemplos do pedido", [route(t).kind for t in (
    "Ceci, abre as configurações.", "Mostra minhas atividades.", "Fica quietinha.", "Vai dormir.",
    "Abre a atividade de Pesquisa Operacional.", "Oi, Ceci.", "Me explica recursividade.",
    "Conta uma piada.", "Tenho atividade amanhã?", "Quais trabalhos estão atrasados?",
    "O que preciso entregar essa semana?", "Me ajuda a organizar meu cronograma.",
    "Qual atividade vence primeiro?")] == ["local"] * 5 + ["conversa"] * 3 + ["academico"] * 5)
check("roteador: frase parecida não vira ação (\"vai dormir cedo hoje?\" é conversa)",
      route("você vai dormir cedo hoje?").kind != "local")
check("roteador: prazo de outra pessoa não puxa seus dados", route("minha mãe tá com prazo no trabalho dela").kind
      == "conversa")

# texto do modelo nunca vira comando
prov.script = ["[neutra] abre as configurações"]
send("diz \"abre as configurações\"")
check("resposta da IA dizendo um comando não executa nada", app.dlg is None)

# balões
long = "Frase de teste com algumas palavras. " * 60
b, cut = prompts.balloons(long)
check("resposta longa: até 5 balões e o resto fica no chat", len(b) == 5 and cut and "chat" in b[-1])

srv.shutdown()
print(f"\n{len(fails)} falha(s)" if fails else "\ntudo ok")
sys.exit(1 if fails else 0)
