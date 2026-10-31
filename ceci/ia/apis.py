"""Provedores de IA pela API oficial de cada serviço (HTTPS, chave do próprio usuário). Só texto entra e sai.

Formato OpenAI (chat/completions): OpenAI, Groq, Gemini, OmniRoute, Cerebras, GitHub Models, OpenRouter.
Formato Anthropic (messages): Claude.
"""
import json
import re
import socket
import urllib.error
import urllib.request

from . import keys
from .provider import AIError, AIProvider, Reply

MAX_OUT = 1024  # tokens de resposta (o balão usa bem menos; o chat mostra tudo)
DAILY = re.compile(r"per day|perday|daily|\bRPD\b|\bTPD\b|insufficient_quota|credit", re.I)
WAIT = re.compile(r"try again in (?:(\d+)h)?(?:(\d+)m(?!s))?(?:([\d.]+)s)?|\"retryDelay\":\s*\"([\d.]+)s", re.I)
DAILY_WAIT = 3 * 3600  # cota do dia (ou crédito) acabou sem dizer quando volta: tenta de novo daqui a 3 h


def wait_of(headers, body):
    """Segundos até o serviço aceitar de novo: Retry-After, "try again in 7m12s", "retryDelay": "36s"."""
    try:
        return max(float(headers.get("Retry-After")), 1.0)
    except (TypeError, ValueError):
        pass
    m = WAIT.search(body)
    if m and any(m.groups()):
        h, mi, s, delay = m.groups()
        return float(delay) if delay else int(h or 0) * 3600 + int(mi or 0) * 60 + float(s or 0)
    return DAILY_WAIT if DAILY.search(body) else None


def _message(body):
    try:
        d = json.loads(body)
        d = d[0] if isinstance(d, list) else d
        err = d.get("error", d)
        msg = err.get("message", "") if isinstance(err, dict) else str(err)
    except (ValueError, AttributeError, IndexError):
        msg = body
    return keys.scrub(" ".join(msg.split()))[:200]


def turns(prompt):
    """Histórico + mensagem atual em papéis alternados, começando pelo usuário (exigência de alguns serviços)."""
    out = []
    for role, text in list(prompt.history) + [("user", prompt.message)]:
        role = "assistant" if role == "ceci" else "user"
        if out and out[-1]["role"] == role:
            out[-1]["content"] += "\n\n" + text
        else:
            out.append({"role": role, "content": text})
    while out and out[0]["role"] != "user":
        out.pop(0)
    return out


class APIProvider(AIProvider):
    """Um modelo de um serviço. A chave vem de keys.py na hora de cada envio."""

    def __init__(self, service, label, url, model, extra=None):
        self.service, self.label, self.url, self.model = service, label, url, model
        self.extra = dict(extra or {})
        self.id = f"{service}/{model}"
        self.name = label

    def key(self):
        return keys.get(self.service)

    def is_available(self):
        return (True, "") if self.key() else (False, f"sem chave do {self.label}")

    def send_message(self, prompt, timeout):
        body, headers = self.request(prompt, self.key() or "")
        if prompt.max_out:
            for k in ("max_tokens", "max_completion_tokens"):
                if k in body:
                    body[k] = prompt.max_out
        return self.reply(self._post(body, headers, timeout))

    def _post(self, body, headers, timeout):
        req = urllib.request.Request(self.url, json.dumps(body).encode(),
                                     {"Content-Type": "application/json", "User-Agent": "CeciBot", **headers})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            raise self._error(e.code, e.headers, e.read(8000).decode("utf8", "replace")) from None
        except (socket.timeout, TimeoutError):
            raise AIError("timeout", f"{self.label} demorou mais de {timeout:.0f} s") from None
        except urllib.error.URLError as e:
            if isinstance(e.reason, (socket.timeout, TimeoutError)):
                raise AIError("timeout", f"{self.label} demorou mais de {timeout:.0f} s") from None
            raise AIError("conexao", f"{self.label}: {e.reason}") from None
        except OSError as e:
            raise AIError("conexao", f"{self.label}: {e}") from None
        except ValueError:
            raise AIError("falha", f"{self.label} devolveu algo que não é JSON") from None

    def _error(self, code, headers, body):
        msg = _message(body)
        if code in (401, 403) or (code == 400 and re.search(r"api.?key", body, re.I)):
            return AIError("sessao", f"{self.label}: chave recusada ({code}) {msg}")
        if code == 404:
            return AIError("indisponivel", f"{self.label}: modelo {self.model} não encontrado")
        if code in (413, 429) or re.search(r"insufficient_quota|RESOURCE_EXHAUSTED", body):
            return AIError("limite", f"{self.label}: {msg}", wait=wait_of(headers, body))
        if code >= 500:
            return AIError("conexao", f"{self.label}: erro {code} do serviço")
        return AIError("falha", f"{self.label}: {code} {msg}")


class OpenAICompat(APIProvider):
    def request(self, prompt, key):
        body = {"model": self.model, "messages": [{"role": "system", "content": prompt.system}] + turns(prompt),
                **self.extra}
        if prompt.json:
            body["response_format"] = {"type": "json_object"}
        return body, ({"Authorization": f"Bearer {key}"} if key else {})

    def reply(self, d):
        try:
            choice = d["choices"][0]
            text = choice["message"].get("content") or ""
        except (KeyError, IndexError, TypeError, AttributeError):
            raise AIError("falha", f"{self.label}: resposta sem texto") from None
        return Reply(text, complete=choice.get("finish_reason") != "length")


class Claude(APIProvider):
    def request(self, prompt, key):
        body = {"model": self.model, "max_tokens": MAX_OUT, "system": prompt.system, "messages": turns(prompt),
                **self.extra}
        return body, {"x-api-key": key, "anthropic-version": "2023-06-01"}

    def reply(self, d):
        text = "".join(b.get("text", "") for b in d.get("content") or [] if b.get("type") == "text")
        return Reply(text, complete=d.get("stop_reason") != "max_tokens")
