"""Cérebro da Ceci (falas e vontades da IA) com um provedor falso. Uso: python tests/live_test.py"""
import os
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["CECI_CONFIG_DIR"] = tempfile.mkdtemp(prefix="cecibot_live_")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json  # noqa: E402
import time  # noqa: E402
from types import SimpleNamespace as NS  # noqa: E402

from PySide6.QtCore import QCoreApplication, QEventLoop  # noqa: E402

from ceci.behavior import Behavior  # noqa: E402
from ceci.ia import prompts  # noqa: E402
from ceci.ia.apis import OpenAICompat  # noqa: E402
from ceci.ia.assistant import Assistant  # noqa: E402
from ceci.ia.context import Conversation  # noqa: E402
from ceci.ia.live import CATS, Mind, now_text  # noqa: E402
from ceci.ia.provider import AIError, AIProvider, Prompt, Reply  # noqa: E402
from ceci.sala.store import Store  # noqa: E402
from ceci.speech import Speech  # noqa: E402

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
        return Reply(r)


class S(dict):
    def save(self):
        pass


GOOD = json.dumps({"humor": "sonolenta", "vontades": ["cafe", "lendo", "voar"],
                   "falas": {"idle": ["[feliz] Puta merda, sábado à noite.", "Que tédio, porra."],
                             "cafe": ["Café, caralho."], "inventada": ["x"], "lendo": [3, ""]}})
clock = [1_793_570_000.0]  # 31/10/2026 à noite (horário local)
fake = Fake()
conv = Conversation(os.path.join(TMP, "c.json"))
conv.add("user", "meu gato chama Biscoito")
conv.add("ceci", "Anotado, porra.")
persona = NS(instructions=lambda: "PERSONALIDADE", key=("p", 1, 1))
m = Mind(fake, persona, conv, Store(os.path.join(TMP, "s.db")), S(ai_academic=None), ["cafe", "lendo", "gato"],
         clock=lambda: clock[0], path=os.path.join(TMP, "mente.json"))

# 1. pedido: personalidade, data/hora, conversa, situações, vontades, JSON
fake.replies.append("```json\n" + GOOD + "\n```")
check("pede na hora certa", m.maybe_refresh() and wait(lambda: not m.busy))
p = fake.calls[0]
check("pedido leva personalidade, data e hora do PC e a conversa recente",
      p.system == "PERSONALIDADE" and now_text(clock[0]) in p.message and "Biscoito" in p.message)
check("pedido leva todas as situações e só as vontades possíveis, em modo JSON com resposta maior",
      all(f"- {c} (" in p.message for c in CATS) and "cafe, lendo, gato" in p.message and p.json
      and p.max_out >= 3000)
check("sem permissão, nada da faculdade vai no pedido", "FACULDADE" not in p.message)

# 2. resposta: falas limpas, categorias e vontades válidas
check("falas: sem etiqueta de humor, lixo fora", m.lines == {"idle": ["Puta merda, sábado à noite.", "Que tédio, porra."],
                                                             "cafe": ["Café, caralho."]})
check("humor e vontades (só as que existem)", m.mood == "sonolenta" and m.wants == ["cafe", "lendo"])
check("guardado no PC", json.load(open(m.path, encoding="utf8"))["wants"] == ["cafe", "lendo"])

# 3. fala automática usa a da IA primeiro e as prontas de reserva
sp = NS(live=m, last_text={}, bags={}, bank={"idle": ["pronta"]})
got = [Speech.pick(sp, "idle") for _ in range(3)]
check("fala: as da IA (uma vez cada), depois a pronta", got == ["Puta merda, sábado à noite.", "Que tédio, porra.",
                                                                "pronta"])

# 4. rotina: o que ela tá com vontade fica 3x mais provável
anims = {"cafe": {"auto": 2}, "gato": {"auto": 2}}
b = NS(win=NS(sprites=NS(anims=anims)), s={"specials": False, "walk": False}, recent=[], last_special=0,
       last_user=time.monotonic(), mind=m)
import random  # noqa: E402
seen = []
orig = random.choices
random.choices = lambda keys, weights: seen.append(dict(zip(keys, weights))) or [keys[0]]
Behavior._choose(b)
random.choices = orig
check("rotina: vontade da IA pesa 3x", seen[0]["cafe"] == 6 and seen[0]["gato"] == 2)

# 5. não pede à toa; erro não apaga as falas que já tem
check("não pede de novo antes do tempo", not m.maybe_refresh())
clock[0] += 9 * 60
fake.replies[:] = [GOOD]
check("depois de uma conversa (8 min+), renova", m.maybe_refresh(after_chat=True) and wait(lambda: not m.busy)
      and m.lines.get("cafe") == ["Café, caralho."])
fake.replies[:] = ["isso não é json"]
clock[0] += 3600
m.lines = {"cafe": ["guardada"]}
m.maybe_refresh()
wait(lambda: not m.busy)
check("JSON quebrado: mantém o que tinha e anota o erro", m.lines == {"cafe": ["guardada"]} and m.last_error)
clock[0] += 3600
fake.replies[:] = [AIError("limite", "todas no limite")]
m.maybe_refresh()
wait(lambda: not m.busy)
check("IA no limite: mantém as falas", m.lines == {"cafe": ["guardada"]} and "limite" in m.last_error)
m2 = Mind(fake, persona, conv, None, S(), [], path=m.path)
check("reabrir: carrega o que estava guardado", m2.lines == {"cafe": ["guardada"]})

# 6. modo JSON e tamanho da resposta chegam na API
api = OpenAICompat("x", "X", "http://127.0.0.1:9/", "m", {"max_tokens": 1024})
body, _ = api.request(Prompt(system="s", message="m", json=True), "k")
check("API: response_format json_object", body["response_format"] == {"type": "json_object"})

# 7. conversa: data e hora do PC; ação de roleplay vira animação
check("ação *bebe café* → café, *Bowie...* → gato, sem ação → None",
      prompts.action_anim("Relaxa *bebe um gole de café*") == "cafe"
      and prompts.action_anim("*Bowie pula no teclado*") == "gato" and prompts.action_anim("oi") is None)
fake2 = Fake()
fake2.replies.append("[feliz] Opa, porra! *boceja*")
ai = Assistant(fake2, Store(os.path.join(TMP, "s2.db")), S(ai_academic=None),
               conv=Conversation(os.path.join(TMP, "c2.json")), personality=persona, clock=lambda: clock[0])
out = []
ai.answered.connect(out.append)
ai.handle("oi ceci")
wait(lambda: out)
check("conversa: a IA recebe a data e a hora do PC", now_text(clock[0]) in fake2.calls[0].system)
check("conversa: *boceja* na resposta → animação sonolenta (no lugar do humor)", out and out[0]["anim"] == "sonolenta")

print("\n" + ("TUDO OK" if not fails else f"{len(fails)} FALHA(S): {fails}"))
sys.exit(1 if fails else 0)
