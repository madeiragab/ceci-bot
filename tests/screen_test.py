"""Tela sem print velho: contexto marca prints antigos, arquivo só volta quando a pergunta é dele, pedido de olhar
a tela tira print na hora, espiada no navegador (fica quieta quando falha). Uso: python tests/screen_test.py"""
import os
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["CECI_CONFIG_DIR"] = tempfile.mkdtemp(prefix="cecibot_screen_")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import time  # noqa: E402
from types import SimpleNamespace as NS  # noqa: E402

from PySide6.QtCore import QCoreApplication, QEventLoop, QRect  # noqa: E402

from ceci import watch  # noqa: E402
from ceci.desktop import Win  # noqa: E402
from ceci.ia import files, prompts  # noqa: E402
from ceci.ia.assistant import Assistant  # noqa: E402
from ceci.ia.context import Conversation  # noqa: E402
from ceci.ia.provider import AIError, AIProvider, Reply  # noqa: E402
from ceci.sala.store import Store  # noqa: E402
from ceci.sala.texts import norm  # noqa: E402

qa = QCoreApplication(sys.argv)
fails = []
TMP = os.environ["CECI_CONFIG_DIR"]


def check(name, cond):
    print(("ok   " if cond else "FALHA"), name)
    if not cond:
        fails.append(name)


def wait(cond, ms=5000):
    end = time.monotonic() + ms / 1000
    while not cond() and time.monotonic() < end:
        QCoreApplication.processEvents(QEventLoop.AllEvents, 50)
        time.sleep(0.01)
    return cond()


class Fake(AIProvider):
    name = "teste"

    def __init__(self):
        self.calls, self.replies = [], []

    def is_available(self):
        return True, ""

    def send_message(self, prompt, timeout):
        self.calls.append(prompt)
        r = self.replies.pop(0)
        if isinstance(r, Exception):
            raise r
        return Reply(r, provider="fake/visao")


class S(dict):
    def save(self):
        pass


# 1. arquivo: só volta quando a mensagem é uma pergunta sobre ele (palavra inteira), nunca em "boa noite ceci"
BIO = ("Cecília Prado nasceu em Curitiba. Na faculdade conheceu o Veríssimo, olhava as estrelas toda noite e "
       "adotou dois gatos, Ozzy e Bowie. Boa parte da vida dela foi lendo Stephen King.")
for q, want in (("Boa noite ceci", False), ("olha que lindinhaaa", False), ("Boa noite ceci, tudo bem?", False),
                ("oq foi a guerra de secessão?", False), ("e jogos você gosta de quais", False),
                ("quem é o Veríssimo?", True), ("o que diz o arquivo?", True), ("e os gatos, como chamam?", True),
                ("acho que a vida é boa", False)):
    part, _ = files.excerpt(BIO, q, generic=False)
    check(f"arquivo: {q!r} {'puxa' if want else 'não puxa'} o arquivo", bool(part) == want)

# 2. contexto: print velho marcado com a hora; com print novo, o que ela disse dos antigos sai
clock = [1_793_570_000.0]
conv = Conversation(os.path.join(TMP, "c.json"), clock=lambda: clock[0])
conv.add("user", "🖥️ Olha minha tela", route="tela", window="RPG - ChatGPT - Brave")
conv.add("ceci", "Cê tá jogando RPG no ChatGPT, porra?", route="tela")
conv.add("user", "to sim")
conv.add("ceci", "Imaginei.", route="conversa")
conv.add("ceci", "Vídeo de gato, que fofo.", route="tela", auto=True, window="Gatos - YouTube")
hh = time.strftime("%H:%M", time.localtime(clock[0]))
r = conv.recent()
check("contexto: pedido de print vira 'print velho' com a hora", r[0][1].startswith(f"[às {hh} mandei um print"))
check("contexto: o que ela viu fica marcado como velho", r[1][1].startswith(f"[o que você viu no print das {hh}"))
check("contexto: espiada sozinha marcada com a janela", "espiou sozinha" in r[4][1] and "Gatos - YouTube" in r[4][1])
r2 = conv.recent(new_shot=True)
check("contexto: com print novo, os comentários dos prints velhos saem",
      all("RPG no ChatGPT" not in t and "gato" not in t for _, t in r2) and any("to sim" == t for _, t in r2))

# 3. pedido de olhar a tela no chat normal
for t, want in (("olha isso aqui", True), ("tá vendo esse erro?", True), ("o que tá aparecendo na minha tela", True),
                ("ve essa aba", True), ("boa noite ceci", False), ("me conta do teu dia", False),
                ("olha que lindinha", False), ("então dorme linda", False)):
    check(f"pedido de tela: {t!r} → {'print na hora' if want else 'conversa'}",
          bool(prompts.SCREEN_ASK.search(norm(t))) == want)

# 4. look: print novo com hora e janela; resposta fica como tela; nota copiada some
fake = Fake()
persona = NS(instructions=lambda: "PERSONALIDADE", key=("p", 1, 1))
ai = Assistant(fake, Store(os.path.join(TMP, "s.db")), S(ai_academic=True), conv=conv, personality=persona,
               clock=lambda: clock[0])
out = []
ai.answered.connect(out.append)
fake.replies.append("[o que você viu no print das 21:10; velho] [rindo] Agora é o VS Code, caralho.")
ai.look("QUJD", "", "main.py - Visual Studio Code")
wait(lambda: out)
p = fake.calls[-1]
check("look: imagem só nesse pedido, PRINT NOVO com hora e janela",
      p.image == "QUJD" and "PRINT NOVO" in p.message and time.strftime("%H:%M:%S", time.localtime(clock[0]))
      in p.message and "main.py - Visual Studio Code" in p.message)
check("look: o histórico do pedido não leva os comentários de prints velhos",
      all("RPG no ChatGPT" not in t for _, t in p.history))
check("look: nota de contexto copiada pela IA some do texto", out and out[-1]["text"] == "Agora é o VS Code, caralho.")
check("look: resposta guardada como tela (vira print velho depois)",
      conv.messages[-1]["route"] == "tela" and out[-1]["route"] == "tela")

# 5. espiada sozinha (troca de aba): quieta quando falha ou não tem nada; descartada se você falar no meio
peek = Fake()
n = len(out)
peek.replies.append(AIError("limite", "cota"))
check("espiada: começa", ai.peek("QUJD", 'a aba "Gatos - YouTube" no navegador', peek))
wait(lambda: not ai.peeking)
check("espiada: limite/erro fica quieto (nada falado, nada no histórico)",
      len(out) == n and conv.messages[-1]["route"] == "tela" and not conv.messages[-1].get("auto"))
peek.replies.append("[nada]")
ai.peek("QUJD", 'a aba "Nada" no navegador', peek)
wait(lambda: not ai.peeking)
check("espiada: [nada] fica quieto", len(out) == n)
peek.replies.append("[rindo] Vídeo de gato de novo, porra? KKKK\n[aponta: 500, 400]")
ai.peek("QUJD", 'a aba "Gatos 2 - YouTube" no navegador', peek)
wait(lambda: not ai.peeking)
check("espiada: comentário curto com ponto, guardado como espiada (auto) com a janela",
      len(out) == n + 1 and out[-1]["point"] == (0.5, 0.4) and out[-1]["auto"]
      and conv.messages[-1].get("auto") and "Gatos 2" in conv.messages[-1]["window"])
check("espiada: pede PEEK com print, sem travar a conversa", "espiada sozinha" in peek.calls[-1].message
      and peek.calls[-1].image == "QUJD" and ai.busy is None)
peek.replies.append("Olha só.")
ai.peek("QUJD", 'a aba "X" no navegador', peek)
ai.job += 1  # você mandou mensagem enquanto ela espiava
wait(lambda: not ai.peeking)
check("espiada: mensagem sua no meio do caminho descarta a espiada", len(out) == n + 1)

# 6. olho no navegador: título estável, intervalo, aba repetida e abas privadas
check("aba: tira o nome do navegador",
      watch.tab_title("Vídeo - YouTube - Brave") == "Vídeo - YouTube"
      and watch.tab_title("Notícia — Mozilla Firefox") == "Notícia"
      and watch.tab_title("(3) YouTube - Brave") == "YouTube"
      and watch.tab_title("Docs e mais 3 páginas - Pessoal - Microsoft\u200b Edge") == "Docs")
check("aba: anônima, login, banco, e-mail e conversa ficam de fora",
      all(watch.private(t) for t in ("Nova guia", "Entrar - Nubank", "Caixa de entrada (3) - Gmail", "WhatsApp",
                                     "Login | Moodle", "InPrivate")) and not watch.private("Gatos - YouTube"))
now = [1000.0]
fg = [None]
w = watch.Watcher(clock=lambda: now[0], fg=lambda: fg[0])
got = []
w.tab.connect(got.append)


def tick(title, secs, browser=True, hwnd=1, exe="code.exe"):
    end = now[0] + secs
    while now[0] < end:
        fg[0] = Win(hwnd, title, "brave.exe" if browser else exe, QRect(0, 0, 800, 600), True, browser)
        w._tick()
        now[0] += 1


tick("Gatos - YouTube - Brave", 10)
check("olho: nada nos primeiros segundos depois de abrir", not got)
now[0] += watch.START
tick("Gatos - YouTube - Brave", 3)
check("olho: passar correndo pela aba não espia", not got)
tick("Outra aba - Brave", watch.STABLE + 2)
check("olho: parou numa aba → espia uma vez, com o título limpo", len(got) == 1 and got[0].title == "Outra aba")
tick("Terceira - Brave", watch.STABLE + 2)
check("olho: respeita o intervalo entre espiadas", len(got) == 1)
now[0] += watch.GAP
tick("Outra aba - Brave", watch.STABLE + 2)
check("olho: a mesma aba não é comentada de novo tão cedo", len(got) == 1)
tick("Login - Brave", watch.STABLE + 2)
tick("Fulano - WhatsApp", watch.STABLE + 2, browser=False, hwnd=3, exe="whatsapp.exe")
check("olho: login e app de conversa ficam de fora", len(got) == 1)
tick("main.py - Visual Studio Code", watch.STABLE + 2, browser=False, hwnd=2)
check("olho: trocar pra outro programa do PC também espia",
      len(got) == 2 and got[1].title == "main.py - Visual Studio Code" and not got[1].browser)
tick("Quarta aba - Brave", watch.STABLE + 2)
check("olho: respeita o intervalo também entre programas", len(got) == 2)
now[0] += watch.GAP
tick("Quinta aba - Brave", watch.STABLE + 2)
check("olho: aba nova depois do intervalo espia de novo", len(got) == 3 and got[2].title == "Quinta aba")

print("\n" + ("TUDO OK" if not fails else f"{len(fails)} FALHA(S): {fails}"))
sys.exit(1 if fails else 0)
