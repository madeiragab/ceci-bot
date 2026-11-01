"""Pedido de ação ("então dorme, linda", "toma um café aí", "sobe na janela") vira a animação/movimento que já
existe: pela marca [faz: ...] da IA, pelo pedido quando a IA esquece, e mesmo com a IA fora do ar.
Uso: python tests/actions_test.py"""
import os
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["CECI_CONFIG_DIR"] = tempfile.mkdtemp(prefix="cecibot_actions_")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import time  # noqa: E402
from types import SimpleNamespace as NS  # noqa: E402

from PySide6.QtCore import QCoreApplication, QEventLoop  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import main as M  # noqa: E402
from ceci.ia import actions  # noqa: E402
from ceci.ia.assistant import Assistant  # noqa: E402
from ceci.ia.context import Conversation  # noqa: E402
from ceci.ia.personality import Personality  # noqa: E402
from ceci.ia.provider import AIError, AIProvider, Reply  # noqa: E402
from ceci.sala.store import Store  # noqa: E402
from ceci.settings import Settings  # noqa: E402
from ceci.window import CeciWindow  # noqa: E402

qa = QApplication(sys.argv)
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
        return Reply(r)


class S(dict):
    def save(self):
        pass


# 1. comparar o pedido com as ações que existem
for t, want in (("então dorme, linda", "dormir"), ("vai tirar um cochilo", "dormir"), ("toma um café aí", "cafe"),
                ("sobe na janela", "subir"), ("senta na janela", "subir"), ("senta aí", "sentar"),
                ("desce daí", "descer"), ("vai ler um livro", "ler"), ("brinca com o Bowie", "gato"),
                ("dá tchau", "acenar"), ("dança pra mim", "comemorar"), ("se esconde", "esconder"),
                ("Boa noite ceci", None), ("lê esse erro", None), ("que programa é esse", None),
                ("vai tomar no cu", None), ("me fala do teu dia", None),
                ("ontem eu dormi tarde e fui pra aula e depois voltei e fiquei jogando até muito tarde", None)):
    check(f"pedido {t!r} → {want}", actions.wanted(t) == want)
check("toda ação aponta para animação que existe ou movimento do App",
      all(a.startswith("_") or a in CeciWindow.__init__.__globals__["Sprites"](0.25).anims
          for _, a, _ in actions.ACTIONS.values()))

# 2. a IA recebe a lista e marca [faz: ...]; sem marca vale o pedido; recusa não vira ação
fake = Fake()
ai = Assistant(fake, Store(os.path.join(TMP, "s.db")), S(ai_academic=True),
               conv=Conversation(os.path.join(TMP, "c.json")), personality=Personality())
out, bad = [], []
ai.answered.connect(out.append)
ai.failed.connect(bad.append)
fake.replies.append("[feliz] Tá bom, porra, boa noite *boceja* [faz: dormir]")
ai.handle("então dorme linda")
wait(lambda: out)
check("IA: a personalidade leva a lista de ações do corpo", "AÇÕES DO SEU CORPO" in fake.calls[-1].system
      and "dormir (tirar um cochilo" in fake.calls[-1].system)
check("IA marcou [faz: dormir] → ação dormir, marca some do texto",
      out[-1]["action"] == "dormir" and "[faz" not in out[-1]["text"] and "faz:" not in ai.conv.messages[-1]["text"])
fake.replies.append("[neutra] Beleza, vou lá então.")
ai.handle("toma um café aí")
wait(lambda: len(out) > 1)
check("IA esqueceu a marca → o pedido do usuário vale (café)", out[-1]["action"] == "cafe")
fake.replies.append("[negando] Nem fodendo que eu vou dormir agora, tá cedo.")
ai.handle("vai dormir agora ceci")
wait(lambda: len(out) > 2)
check("ela recusou → não dorme", out[-1]["action"] is None)
fake.replies.append("[curiosa] Voar eu não sei não, mano. [faz: voar]")
ai.handle("voa pela tela")
wait(lambda: len(out) > 3)
check("marca de ação que não existe é ignorada (e some do texto)",
      out[-1]["action"] is None and "faz" not in out[-1]["text"])
fake.replies.append(AIError("limite", "cota"))
ai.handle("então dorme linda")
wait(lambda: bad)
check("IA fora do ar: ela dorme mesmo assim", bad and bad[-1]["action"] == "dormir")

# 3. o App faz de verdade (janela real, sem tela)
s = Settings()
s.save = lambda: None
s["follow_mouse"] = False
win = CeciWindow(s)
win.set_start_pos()
win.show()
said = []
app = NS(win=win, s=s, hold="x", beh=NS(user_activity=lambda: None), stroll=lambda: said.append("passeou"),
         speech=NS(say_many=lambda lines: said.extend(lines), muted=None),
         _say=lambda aid, lines: said.append(("say", aid)))
M.App._act(app, "dormir", ["Boa noite, porra."])
check("App: dormir → cochilo de verdade, com a fala", win.player.aid == "cochilo" and "Boa noite, porra." in said)
M.App._act(app, "cafe", ["Café."])
wait(lambda: win.player.aid == "cafe", 10000)  # acorda pelos quadros do cochilo e então pega o café
check("App: café → animação do café, sem segurar até a fala acabar", win.player.aid == "cafe" and app.hold is None)
M.App._act(app, "passear", ["Fui."])
check("App: passear anda", "passeou" in said)
said.clear()
M.App._act(app, "subir", ["Subi!"])
check("App: subir sem janela livre avisa em vez de fingir", any("Não tem janela" in str(x) for x in said))

said.clear()
moved = []
app._point = lambda pt, lines: moved.append("apontou")
app._act = lambda action, lines: moved.append(action)
app.screen_geom = object()
M.App._answered(app, {"auto": True, "route": "tela", "point": (0.9, 0.5), "action": "subir", "anim": "observando",
                      "balloons": ["Olha isso."]})
check("espiada sozinha (trocou de janela): só comenta, não anda até o ponto nem faz ação",
      not moved and ("say", "observando") in said)
M.App._answered(app, {"route": "tela", "point": (0.9, 0.5), "anim": "observando", "balloons": ["Ali."]})
check("Ctrl+Alt+C continua apontando", moved == ["apontou"])

print("\n" + ("TUDO OK" if not fails else f"{len(fails)} FALHA(S): {fails}"))
sys.exit(1 if fails else 0)
