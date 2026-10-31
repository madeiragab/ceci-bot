"""Provedor Gemini Web: avaliado e mantido desligado (motivo em BLOCKED).

Avaliação feita em 31/10/2026:
- https://gemini.google.com/robots.txt tem "User-agent: *", "Disallow: /app/" e "Disallow: /chat/": as páginas
  do chat estão fechadas para acesso automatizado.
- Os Termos de Serviço do Google listam como abuso "usar meios automatizados para acessar conteúdo de
  qualquer um dos nossos serviços em violação das instruções legíveis por máquina" das páginas (como o robots.txt).
- Playwright digitando na página e uma extensão que digita por você são o mesmo acesso automatizado.
  Os caminhos que sobram (endpoints internos, cookies copiados, disfarçar o navegador automatizado) são
  justamente os proibidos pelo pedido.
Conclusão: não há como automatizar o Gemini Web de forma permitida. A Ceci funciona sem IA (comandos e
respostas locais) e aceita outro provedor pela interface AIProvider, escolhido em settings.json ("ai_provider").
"""
from .provider import AIError, AIProvider

BLOCKED = ("O Gemini Web não pode ser automatizado de forma permitida: o robots.txt do gemini.google.com fecha as "
           "páginas do chat (/app/ e /chat/) para automação, e os Termos do Google tratam esse acesso como abuso.")


class GeminiWebProvider(AIProvider):
    name = "Gemini Web"

    def is_available(self):
        return False, BLOCKED

    def send_message(self, prompt, timeout):
        raise AIError("indisponivel", BLOCKED)
