"""Fase 3: a IA da Ceci (núcleo independente do provedor).

roteador → comando local | pergunta com dados da Sala Virtual | conversa
personalidade (ceci_personality.txt) + contexto compacto + dados locais → AIProvider → resposta no balão.
O provedor é trocável: o resto do app só conhece a interface AIProvider (provider.py).
"""
from .chain import ChainProvider, build
from .gemini_web import GeminiWebProvider

PROVIDERS = {"corrente": ChainProvider, "gemini_web": GeminiWebProvider}


def make_provider(name, chain=None):
    if name in ("corrente", None) or name not in PROVIDERS:
        return ChainProvider(build(chain))
    return PROVIDERS[name]()
