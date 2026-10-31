"""Contrato do provedor de IA. O resto da Ceci só fala com esta interface: trocar de provedor não muda o app."""
from dataclasses import dataclass, field


class AIError(Exception):
    """Falha do provedor. `kind` decide o que a Ceci fala; `partial` guarda o que chegou antes de cortar."""
    KINDS = ("indisponivel", "sessao", "conexao", "timeout", "vazia", "incompleta", "cancelada", "limite", "falha")

    def __init__(self, kind, message="", partial=""):
        super().__init__(message or kind)
        self.kind = kind if kind in self.KINDS else "falha"
        self.partial = partial


@dataclass
class Prompt:
    system: str                 # personalidade + regras do app
    message: str                # a mensagem desta vez (com os dados da Sala Virtual, quando precisa)
    history: list = field(default_factory=list)  # [(papel, texto)] recentes e curtos: "user" | "ceci"
    new_session: bool = True    # True: o provedor precisa receber a personalidade de novo (início ou reinício)
    session_id: str = None      # conversa do provedor que deve continuar (quando ele guarda a conversa)


@dataclass
class Reply:
    text: str
    complete: bool = True       # False: a resposta chegou cortada
    session_id: str = None      # conversa do provedor, para continuar na próxima


class AIProvider:
    """send_message roda numa thread de trabalho; cancel pode vir de outra thread (a da interface)."""
    name = "?"

    def is_available(self):
        """(disponível, motivo legível quando não está)."""
        raise NotImplementedError

    def send_message(self, prompt, timeout):
        """Devolve Reply ou levanta AIError. Nunca executa nada: só texto entra e sai."""
        raise NotImplementedError

    def reset_session(self):
        """Esquece a conversa do lado do provedor (a próxima mensagem leva a personalidade de novo)."""

    def cancel(self):
        """Interrompe o envio em andamento, se houver."""

    def close(self):
        """Libera o que estiver aberto (conexões, processos). Chamado ao sair."""
