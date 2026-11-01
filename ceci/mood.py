"""Humor da Ceci nas interações: clique, carinho e "Interagir" não tocam sempre a mesma animação.

Ela reage conforme o momento: feliz, fofa, apaixonadinha... ou brava, se você não para de mexer nela, se
interrompeu o que ela tava fazendo ou se acabou de acordá-la. Só usa animações que já existem; depois da reação
ela volta pro idle (o "next" de todas elas). Dormindo, o clique só acorda (a animação de acordar já é a reação).
"""
import random

WINDOW = 60.0     # s: interações contadas para "já chega"
ANNOYED = 6       # tantas em WINDOW: quase sempre brava
TIRED = 4         # a partir daqui começa a poder ficar brava
GRUMPY = 20.0     # s depois de acordar: mal-humorada
BUSY = frozenset(("lendo", "lendo_chao", "cafe", "caneca", "programando", "programando_mesa", "trabalhando",
                  "gato", "testes", "corrigindo_bug", "encontrando_bug", "resumo", "tarefa"))

# reação → peso, por tipo de interação (feliz de vários jeitos; a brava entra pelos pesos de humor)
HAPPY = {
    "carinho": {"carinho": 3, "feliz": 2, "apaixonada": 2, "fofa": 1},
    "clique": {"feliz": 2, "acenando": 1, "fofa": 1, "coracao": 1, "beijinho": 1, "apaixonada": 1, "confusa": 1},
}
SAY = {"carinho": "carinho", "clique": "clique"}  # categoria de fala da reação feliz; brava fala "brava"


class Mood:
    def __init__(self, rng=random):
        self.rng = rng
        self.hits = []      # momentos das últimas interações
        self.woke = -99.0   # quando foi acordada pela última vez

    def woken(self, now):
        self.woke = now
        self.hits.append(now)

    def react(self, kind, doing, now):
        """Animação e categoria de fala para esta interação. kind: "carinho" ou "clique"."""
        self.hits = [t for t in self.hits if now - t < WINDOW] + [now]
        n = len(self.hits)
        angry = 0.0
        if n >= ANNOYED:
            angry = 0.75  # já deu, né
        elif n >= TIRED:
            angry = 0.3
        if doing in BUSY:
            angry = max(angry, 0.35)  # tava ocupada
        if now - self.woke < GRUMPY:
            angry = max(angry, 0.5)  # acabou de acordar
        if self.rng.random() < angry:
            return "brava", "brava"
        table = HAPPY.get(kind, HAPPY["clique"])
        aid = self.rng.choices(list(table), weights=list(table.values()))[0]
        return aid, SAY.get(kind, "clique")
