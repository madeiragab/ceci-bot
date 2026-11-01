"""Humor nas interações: carinho e clique variam a reação (feliz, fofa, apaixonadinha...) e ela fica brava
quando você não para de mexer, interrompe o que ela tava fazendo ou acabou de acordá-la.

Uso: python tests/mood_test.py
"""
import json
import os
import random
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ceci import mood  # noqa: E402

fails = []


def check(name, cond):
    print(("ok   " if cond else "FALHA"), name)
    if not cond:
        fails.append(name)


def many(kind, doing="idle", hits=0, woke=None, n=400):
    out = Counter()
    for i in range(n):
        m = mood.Mood(random.Random(i))
        m.hits = [1000.0 - k for k in range(hits)]
        if woke is not None:
            m.woke = woke
        out[m.react(kind, doing, 1000.0)] += 1
    return out


calm = many("carinho")
check("carinho calmo: nunca brava", not any(a == "brava" for a, _ in calm))
check("carinho calmo: varia (carinho, feliz, apaixonada, fofa)",
      {a for a, _ in calm} == set(mood.HAPPY["carinho"]))
check("carinho feliz fala frase de carinho", all(c == "carinho" for _, c in calm))
click = many("clique")
check("clique calmo: varia entre várias reações e fala de clique",
      len({a for a, _ in click}) >= 5 and all(c == "clique" for _, c in click))
lots = many("carinho", hits=mood.ANNOYED)
check("muito carinho seguido: quase sempre brava (e fala brava)",
      lots[("brava", "brava")] > 0.6 * sum(lots.values()))
some = many("carinho", hits=mood.TIRED)
check("um tanto seguido: às vezes brava", 0.15 < some[("brava", "brava")] / sum(some.values()) < 0.5)
busy = many("clique", doing="lendo")
check("interrompeu a leitura: às vezes brava", busy[("brava", "brava")] > 0.2 * sum(busy.values()))
grumpy = many("carinho", woke=1000.0 - 5)
check("acabou de acordar: mal-humorada", grumpy[("brava", "brava")] > 0.35 * sum(grumpy.values()))
old = many("carinho", woke=1000.0 - mood.GRUMPY - 1)
check("acordou faz tempo: passou", not any(a == "brava" for a, _ in old))
m = mood.Mood(random.Random(1))
for t in range(10):
    m.react("carinho", "idle", 100.0 + t)
m.react("carinho", "idle", 100.0 + 9 + mood.WINDOW)
check("interações antigas esquecidas depois de WINDOW", len(m.hits) <= 2)

names = json.load(open(os.path.join(os.path.dirname(mood.__file__), "..", "assets", "animations.json"), encoding="utf8"))
names = names.get("animations", names)
check("todas as reações são animações que já existem",
      all(a in names for t in mood.HAPPY.values() for a in t) and "brava" in names)

print("\n" + ("tudo certo" if not fails else f"{len(fails)} FALHA(S): {fails}"))
sys.exit(1 if fails else 0)
