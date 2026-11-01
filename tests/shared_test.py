"""Personalidade igual em todos os PCs: mente_ia.json e ceci_personality.txt vão pra pasta compartilhada
(OneDrive); a conversa fica só no PC (em PC novo começa do zero).

Uso: python tests/shared_test.py
"""
import os
import sys
import tempfile
import time

base = tempfile.mkdtemp(prefix="cecibot_test_")
os.environ["CECI_CONFIG_DIR"] = os.path.join(base, "pc")
os.environ["CECI_SHARED_DIR"] = os.path.join(base, "onedrive")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ceci import settings, shared  # noqa: E402
from ceci.ia import context, live, personality  # noqa: E402

fails = []


def check(name, cond):
    print(("ok   " if cond else "FALHA"), name)
    if not cond:
        fails.append(name)


pc, od = os.environ["CECI_CONFIG_DIR"], os.environ["CECI_SHARED_DIR"]
check("pasta compartilhada separada da do PC", settings.SHARED_DIR == od and settings.CONFIG_DIR == pc)
check("humor/falas da IA na pasta compartilhada", os.path.dirname(live.PATH) == od)
check("conversa fica só no PC", os.path.dirname(context.PATH) == pc)
check("personalidade compartilhada vem antes da do PC e da do app",
      personality.Personality().paths[0] == os.path.join(od, "ceci_personality.txt"))

os.makedirs(pc)
for n, t in (("mente_ia.json", '{"mood": "pc"}'), ("ceci_personality.txt", "minha"), ("conversa.json", "{}")):
    open(os.path.join(pc, n), "w", encoding="utf8").write(t)
shared.migrate()
check("migra humor e personalidade deste PC", open(os.path.join(od, "mente_ia.json")).read() == '{"mood": "pc"}'
      and open(os.path.join(od, "ceci_personality.txt")).read() == "minha")
check("conversa não vai pro OneDrive", not os.path.exists(os.path.join(od, "conversa.json"))
      and os.path.exists(os.path.join(pc, "conversa.json")))
check("não migra de novo (backup .migrado)", not os.path.exists(os.path.join(pc, "mente_ia.json"))
      and os.path.exists(os.path.join(pc, "mente_ia.json.migrado")))
# outro PC com humor mais velho: não estraga o compartilhado
open(os.path.join(pc, "mente_ia.json"), "w").write('{"mood": "velho"}')
old = time.time() - 3600
os.utime(os.path.join(pc, "mente_ia.json"), (old, old))
shared.migrate()
check("PC com humor mais velho não sobrescreve o do OneDrive",
      open(os.path.join(od, "mente_ia.json")).read() == '{"mood": "pc"}')
check("personalidade compartilhada é a usada", personality.Personality().text() == "minha")

print("\n" + ("tudo certo" if not fails else f"{len(fails)} FALHA(S): {fails}"))
sys.exit(1 if fails else 0)
