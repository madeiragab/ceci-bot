"""Fase 3: a IA da Ceci (núcleo independente do provedor).

roteador → comando local | pergunta com dados da Sala Virtual | conversa
personalidade (ceci_personality.txt) + contexto compacto + dados locais → AIProvider → resposta no balão.
O provedor é trocável: o resto do app só conhece a interface AIProvider (provider.py).
"""
from .gemini_web import GeminiWebProvider

PROVIDERS = {"gemini_web": GeminiWebProvider}


def make_provider(name):
    return PROVIDERS.get(name, GeminiWebProvider)()
