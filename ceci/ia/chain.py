"""Corrente de provedores: tenta na ordem e, quando um bate no limite (ou cai), passa para o próximo.

Ordem pedida: GPT → Claude → OmniRoute → os grátis cuja cota zera por dia (Groq, Gemini, Cerebras,
GitHub Models, OpenRouter). Sem chave salva, o serviço fica de fora. Um por serviço, com a chave do usuário:
nada de várias contas do mesmo serviço para fugir do limite.

Quem bate no limite fica pausado pelo tempo que o serviço informar (ou 3 h quando é a cota do dia sem prazo),
sem receber pedidos à toa. Quando a IA que vai responder não é a que respondeu a anterior, ela recebe a
conversa inteira em markdown (prompts.SWITCH) para não se perder.
"""
import threading
import time
from dataclasses import replace

from . import prompts
from .apis import MAX_OUT, Claude, OpenAICompat
from .provider import AIError, AIProvider

# serviço: (nome, formato, endereço, corpo padrão, onde pegar a chave)
SERVICES = {
    "openai": ("OpenAI (GPT)", OpenAICompat, "https://api.openai.com/v1/chat/completions",
               {"max_completion_tokens": MAX_OUT}, "platform.openai.com/api-keys"),
    "anthropic": ("Claude", Claude, "https://api.anthropic.com/v1/messages", {}, "console.anthropic.com"),
    "omniroute": ("OmniRoute", OpenAICompat, "http://localhost:20128/v1/chat/completions",
                  {"max_tokens": MAX_OUT}, "painel do OmniRoute (rodando neste PC)"),
    "groq": ("Groq", OpenAICompat, "https://api.groq.com/openai/v1/chat/completions",
             {"max_completion_tokens": MAX_OUT}, "console.groq.com/keys"),
    "gemini": ("Gemini", OpenAICompat, "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
               {"max_tokens": MAX_OUT}, "aistudio.google.com/apikey"),
    "cerebras": ("Cerebras", OpenAICompat, "https://api.cerebras.ai/v1/chat/completions",
                 {"max_completion_tokens": MAX_OUT}, "cloud.cerebras.ai"),
    "github": ("GitHub Models", OpenAICompat, "https://models.github.ai/inference/chat/completions",
               {"max_tokens": MAX_OUT}, "github.com/settings/tokens (permissão Models)"),
    "openrouter": ("OpenRouter", OpenAICompat, "https://openrouter.ai/api/v1/chat/completions",
                   {"max_tokens": MAX_OUT}, "openrouter.ai/keys"),
}
# (serviço, modelo, corpo extra). No Groq e no Gemini cada modelo tem a própria cota diária.
# Modelos que enxergam imagem (print da tela, Ctrl+Alt+C); os outros ficam de fora desses pedidos.
VISION = {"openai/gpt-5-mini", "anthropic/claude-haiku-5-5", "gemini/gemini-3.5-flash-lite", "gemini/gemini-2.5-flash",
          "github/openai/gpt-4.1-mini"}
CHAIN = [
    ("openai", "gpt-5-mini", {"reasoning_effort": "minimal"}),
    ("anthropic", "claude-haiku-5-5", {}),
    ("omniroute", "auto", {}),
    ("gemini", "gemini-3.5-flash-lite", {"reasoning_effort": "low"}),  # melhor no tom da Ceci: antes do Groq
    ("groq", "openai/gpt-oss-120b", {"reasoning_effort": "low"}),
    ("groq", "qwen/qwen3.8-27b", {"reasoning_effort": "none"}),
    ("groq", "openai/gpt-oss-20b", {"reasoning_effort": "low"}),
    ("gemini", "gemini-2.5-flash", {"reasoning_effort": "low"}),
    ("cerebras", "gpt-oss-120b", {}),
    ("github", "openai/gpt-4.1-mini", {}),
    ("openrouter", "openrouter/free", {}),
]
PER_TRY = 30  # segundos por tentativa: um serviço travado não come o tempo dos outros
# quanto tempo cada falha deixa o modelo de fora
PAUSE = {"sessao": 6 * 3600, "indisponivel": 3600}
# qual falha a Ceci conta quando todos falharam: a mais "tenta de novo" primeiro
WORST = ("conexao", "timeout", "falha", "vazia", "incompleta", "sessao", "indisponivel", "limite")


def build(spec=None):
    """Lista de provedores. spec (settings "ai_chain"): ["serviço/modelo", ...] para trocar a ordem padrão."""
    entries = CHAIN
    if spec:
        extra = {(s, m): e for s, m, e in CHAIN}
        entries = [(s, m, extra.get((s, m), {})) for s, _, m in (x.partition("/") for x in spec) if s in SERVICES]
    out = []
    for service, model, extra in entries:
        label, cls, url, body, _ = SERVICES[service]
        out.append(cls(service, label, url, model, {**body, **extra}, vision=f"{service}/{model}" in VISION))
    return out


def pause_for(err):
    if err.kind == "limite":
        return min(max(err.wait or 60, 20), 24 * 3600)
    return PAUSE.get(err.kind, 60)


def when(secs):
    secs = int(secs)
    return f"{secs // 3600}h{secs % 3600 // 60:02d}" if secs >= 3600 else f"{max(secs // 60, 1)} min"


class ChainProvider(AIProvider):
    def __init__(self, entries=None, clock=time.monotonic, per_try=PER_TRY):
        self.entries = build() if entries is None else entries
        self.now, self.per_try = clock, per_try
        self.paused = {}   # id → (até quando, AIError)
        self.last = None   # id de quem respondeu por último
        self._stop = threading.Event()

    @property
    def name(self):
        names = []
        for p in self.entries:
            if p.label not in names and p.is_available()[0]:
                names.append(p.label)
        if not names:
            return "provedor de IA"
        return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " ou " + names[-1]

    def is_available(self):
        if any(p.is_available()[0] for p in self.entries):
            return True, ""
        return False, "nenhuma chave de IA salva (botão direito → Abrir chat → Chaves)"

    def send_message(self, prompt, timeout):
        self._stop.clear()
        end = self.now() + timeout
        errors = []
        for p in self.entries:
            if not p.is_available()[0] or (prompt.image and not getattr(p, "vision", False)):
                continue
            until, err = self.paused.get(p.id, (0, None))
            if until > self.now():
                errors.append(err)
                continue
            left = end - self.now()
            if left < 2:
                errors.append(AIError("timeout"))
                break
            try:
                r = p.send_message(self._for(p, prompt), min(left, self.per_try))
                if not (r.text or "").strip():
                    raise AIError("vazia", f"{p.label} devolveu resposta vazia")
            except AIError as e:
                if self._stop.is_set():
                    raise AIError("cancelada") from None
                self.paused[p.id] = (self.now() + pause_for(e), e)
                errors.append(e)
                continue
            if self._stop.is_set():
                raise AIError("cancelada")
            self.paused.pop(p.id, None)
            self.last = r.provider = p.id
            return r
        if not errors:
            raise AIError("indisponivel", "nenhuma IA que enxerga imagem tem chave" if prompt.image
                          else self.is_available()[1])
        kinds = [e.kind for e in errors]
        worst = next(k for k in WORST + (kinds[0],) if k in kinds)
        e = next(e for e in errors if e.kind == worst)
        if worst == "limite":
            wait = min(until - self.now() for until, _ in self.paused.values())
            raise AIError("limite", f"todas as IAs no limite; a primeira volta em {when(wait)}", wait=wait)
        raise e

    def _for(self, p, prompt):
        """Outra IA assumindo: em vez das últimas mensagens, ela recebe a conversa inteira em markdown."""
        if not prompt.transcript or prompt.last_provider == p.id:
            return prompt
        return replace(prompt, history=[], system=prompt.system + "\n\n" + prompts.SWITCH + prompt.transcript)

    def forget(self, service):
        """Chave trocada: o serviço volta a ser tentado na hora."""
        for k in [k for k in self.paused if k.split("/", 1)[0] == service]:
            del self.paused[k]

    def describe(self):
        """Uma linha por modelo com chave: pronto, pausado (até quando e por quê)."""
        out = []
        for p in self.entries:
            if not p.is_available()[0]:
                continue
            until, err = self.paused.get(p.id, (0, None))
            mark = " (respondeu por último)" if p.id == self.last else ""
            state = f"pausado {when(until - self.now())}: {err}" if until > self.now() else "pronto"
            out.append(f"{p.label} · {p.model}: {state}{mark}")
        return out

    def cancel(self):
        self._stop.set()
