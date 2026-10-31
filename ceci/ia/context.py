"""Conversa da Ceci: histórico completo (para a janela do chat) + contexto compacto (para o modelo).

Guardado em %APPDATA%\\Ceci Bot\\conversa.json. Fechar a janela do chat ou o navegador não apaga nada;
só "Apagar histórico" apaga. Para o modelo vão só as últimas mensagens, encurtadas.
"""
import json
import os
import time

from ..settings import CONFIG_DIR

PATH = os.path.join(CONFIG_DIR, "conversa.json")
KEEP = 400          # mensagens guardadas no histórico
RECENT = 8          # mensagens que vão para o modelo
RECENT_CHARS = 600  # cada uma, no máximo
STATE = {"session_id": None, "last_topic": None, "last_keys": [], "last_module": None, "last_at": None,
         "personality_key": None, "provider": None, "file": None}


class Conversation:
    def __init__(self, path=PATH, clock=time.time):
        self.path, self.now = path, clock
        self.messages, self.state = [], dict(STATE)
        try:
            with open(path, encoding="utf8") as f:
                data = json.load(f)
            self.messages = data.get("messages", [])[-KEEP:]
            self.state.update({k: v for k, v in data.get("state", {}).items() if k in STATE})
        except (OSError, ValueError):
            pass

    def save(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf8") as f:
            json.dump({"messages": self.messages[-KEEP:], "state": self.state}, f, ensure_ascii=False, indent=0)
        os.replace(tmp, self.path)

    def add(self, role, text, **extra):
        """role: user | ceci | sistema. extra: route, mood, error, complete..."""
        m = {"role": role, "text": text, "at": self.now(), **extra}
        self.messages.append(m)
        self.state["last_at"] = m["at"]
        self.save()
        return m

    def recent(self, n=RECENT, chars=RECENT_CHARS):
        """Últimas trocas da conversa atual, curtas, sem mensagens de erro (o que o modelo precisa para seguir)."""
        out = []
        for m in reversed(self.messages):
            if m["role"] == "sistema":
                break  # começo da conversa atual
            if m.get("error") or m.get("route") == "local":
                continue
            t = m["text"] if len(m["text"]) <= chars else m["text"][:chars - 1] + "…"
            out.append((m["role"], t))
            if len(out) >= n:
                break
        return out[::-1]

    def remember(self, **kw):
        self.state.update({k: v for k, v in kw.items() if k in STATE})
        self.save()

    def new_session(self, note="Nova conversa"):
        """Esquece o contexto (e a conversa do provedor), mas mantém o histórico na janela."""
        self.state.update(session_id=None, last_topic=None, last_keys=[], last_module=None, provider=None, file=None)
        self.add("sistema", note)

    def clear(self):
        self.messages, self.state = [], dict(STATE)
        self.save()
