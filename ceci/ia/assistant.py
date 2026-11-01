"""Orquestra a conversa: roteia, junta personalidade + contexto + dados, chama o provedor numa thread e
devolve a resposta pronta para o balão. O texto do modelo nunca é executado: comandos só pelo roteador.
"""
import os
import threading
import time

from PySide6.QtCore import QObject, QTimer, Signal

from ..sala import texts
from . import academic, actions, files, live, prompts, router
from .context import Conversation
from .personality import Personality
from .provider import AIError

FAIL = {
    "indisponivel": "Ainda não tenho uma IA conectada pra conversar. Os comandos funcionam: digita \"ajuda\".",
    "sessao": "A chave da IA foi recusada. Confere em botão direito → Abrir chat → Chaves.",
    "conexao": "Puta merda, a conexão com a IA caiu. Digita \"tenta de novo\" que eu mando outra vez.",
    "timeout": "A IA demorou demais e eu desisti de esperar. \"tenta de novo\"?",
    "vazia": "A IA me devolveu um nada. KKKKK. \"tenta de novo\"?",
    "incompleta": "A resposta veio cortada. \"tenta de novo\" pede outra.",
    "limite": "Todas as IAs que eu tenho bateram no limite por enquanto. Tenta mais tarde.",
    "falha": "Deu ruim aqui com a IA. \"tenta de novo\"?",
    "cancelada": "Beleza, deixei essa pra lá.",
}
SLOW = 1200  # ms até "pensando" virar "processando"


class Assistant(QObject):
    state = Signal(str)        # atencao | pensando | processando
    answered = Signal(dict)    # resposta da IA: text, balloons, truncated, mood, anim, route
    failed = Signal(dict)      # falha: kind, say (frases), anim
    speak = Signal(object, list)  # fala local (animação ou None, frases): respostas sem IA, avisos
    local = Signal(str, str)   # comando local que o App executa: (ação, resto)
    changed = Signal()         # histórico mudou (janela do chat)
    _done = Signal(object)     # thread de trabalho → thread da interface
    _peeked = Signal(object)   # espiada sozinha terminou (thread → interface)

    def __init__(self, provider, store, settings, conv=None, personality=None, clock=time.time, timeout=90):
        super().__init__()
        self.provider, self.store, self.s = provider, store, settings
        self.conv = conv or Conversation()
        self.persona = personality or Personality()
        self.now, self.timeout = clock, timeout
        self.busy = None             # mensagem esperando a IA (bloqueia envio duplicado)
        self.job = 0                 # número do envio: resposta de envio cancelado/expirado é descartada
        self.retry_text = None       # última que falhou ("tenta de novo")
        self.consent_pending = None  # pergunta acadêmica esperando "sim" para mandar os dados
        self.files = {}              # caminho → texto inteiro dos arquivos entregues (só na memória)
        self.fresh_file = False      # o próximo envio é a entrega do arquivo (depois ele vai só como consulta)
        self.peeking = False         # espiada sozinha (troca de aba) esperando a IA
        self.watchdog = QTimer(self, singleShot=True, timeout=self._expired)
        self._done.connect(self._finish)
        self._peeked.connect(self._peek_done)

    # --- entrada ---
    def handle(self, text):
        text = text.strip()
        if not text:
            return
        r = self._route(text)
        if r.kind == "local":
            self.conv.add("user", text, route="local")
            self.changed.emit()
            return self._local(r.action, r.rest)
        self.state.emit("atencao")
        self.ask(text, r)

    def _route(self, text):
        return router.route(text, self.conv.state["last_topic"], academic.course_names(self.store),
                            self.consent_pending is not None)

    def _local(self, action, rest):
        if action == "cancelar":
            return self.cancel()
        if action == "de_novo":
            return self.retry()
        if action == "nova_conversa":
            self.reset()
            return self._say(None, ["Beleza, conversa nova. Do zero."])
        if action in ("dados_sim", "dados_nao"):
            return self._consent(action == "dados_sim")
        self.local.emit(action, rest)

    def _consent(self, yes):
        self.s["ai_academic"] = yes
        self.s.save()
        pend, self.consent_pending = self.consent_pending, None
        if yes:
            self._say("feliz", ["Fechado: mando só o recorte das atividades que cada pergunta pedir."])
        else:
            self._say(None, ["Tranquilo, não mando. Respondo com os dados daqui mesmo."])
        if pend:
            self.ask(pend, self._route(pend), logged=True)

    # --- pergunta para a IA ---
    def ask(self, text, r, logged=False, image=None, where=""):
        if self.busy:
            if texts.norm(text) == texts.norm(self.busy):
                return  # mesma mensagem de novo enquanto espera: não manda duas vezes
            return self._say("negando", ["Calma, ainda tô pensando na anterior. Digita \"para\" pra cancelar."])
        if not logged:
            self.conv.add("user", text, route=r.kind)
            self.changed.emit()
        ok, why = self.provider.is_available()
        if r.kind == "academico" and (not ok or self.s.get("ai_academic") is False):
            return self._local_answer(r)  # sem IA (ou sem permissão): os dados locais respondem sozinhos
        if not ok:
            return self._fail(AIError("indisponivel", why), text, r.kind)
        ctx = keys = None
        if r.kind == "academico":
            if self.s.get("ai_academic") is None:
                self.consent_pending = text
                return self._say("curiosa", [f"Pra responder isso eu mando pro {self.provider.name} só o recorte "
                                             "das suas atividades (disciplina, título, prazo e status). Posso? "
                                             "Responde \"sim\" ou \"não\"."])
            ctx, keys = academic.build(self.store, r.rest, self.now(), self.conv.state["last_keys"],
                                       follow=r.action == "seguimento")
        try:
            system = self.persona.instructions() + f"\n\nAGORA (data e hora do PC): {live.now_text(self.now())}"
        except OSError:
            return self._fail(AIError("falha", "ceci_personality.txt não encontrado"), text, r.kind)
        pkey = list(self.persona.key)
        new = self.conv.state["session_id"] is None or self.conv.state["personality_key"] != pkey
        history = self.conv.recent(new_shot=bool(image))[:-1]  # a mensagem atual vai em prompt.message
        prompt = prompts.build(system, history, text, ctx, new, self.conv.state["session_id"])
        # se outra IA assumir, ela recebe a conversa inteira em markdown (ChainProvider decide)
        prompt.transcript = prompts.markdown(
            self.conv.recent(prompts.TRANSCRIPT, prompts.TRANSCRIPT_CHARS, new_shot=bool(image))[:-1])
        prompt.last_provider = self.conv.state["provider"]
        f = self.conv.state.get("file")
        body = self._file_text(f) if f else None
        fresh, self.fresh_file = self.fresh_file, False
        if body:  # arquivo que o usuário mandou: na entrega vai como novo; depois, só como consulta quando a
            # mensagem fala de algo que está nele (até a próxima "nova conversa" ou outro arquivo)
            part, how = files.excerpt(body, text, generic=fresh)
            cut = (f"Ele tem {len(body)} caracteres; você recebeu {how} (marcados [trecho N de M]). Se a resposta "
                   "não estiver nesses trechos, diga isso em vez de inventar.") if how else ""
            if part:
                tpl = prompts.FILE if fresh else prompts.FILE_REF
                prompt.message = tpl.format(name=f["name"], text=part, cut=cut) + "\n\n" + prompt.message
        if image:  # print da tela tirado agora: vai só nesta mensagem
            prompt.image = image
            prompt.message = (prompts.SCREEN.format(when=self._clock(), where=f', janela em foco: "{where}"' if where
                                                    else "") + "\n\nO QUE O USUÁRIO DISSE: " + prompt.message)
        self.busy, self.retry_text = text, None
        self.job += 1
        meta = {"job": self.job, "text": text, "route": r.kind, "keys": keys, "ctx": ctx, "pkey": pkey}
        self.state.emit("pensando")
        threading.Thread(target=self._work, args=(prompt, meta), daemon=True).start()
        QTimer.singleShot(SLOW, lambda j=self.job: self.busy and self.job == j and self.state.emit("processando"))
        self.watchdog.start(int((self.timeout + 5) * 1000))

    def _work(self, prompt, meta):
        try:
            self._done.emit((meta, self.provider.send_message(prompt, self.timeout), None))
        except AIError as e:
            self._done.emit((meta, None, e))
        except Exception as e:  # provedor com defeito não derruba a Ceci
            self._done.emit((meta, None, AIError("falha", str(e))))

    def _finish(self, res):
        meta, reply, err = res
        if meta["job"] != self.job or self.busy is None:
            return  # cancelada ou expirada: o que chegou depois é descartado
        self.watchdog.stop()
        self.busy = None
        if err is None and not (reply.text or "").strip():
            err = AIError("vazia")
        if err is not None:
            if err.kind == "incompleta" and err.partial.strip():
                return self._answer(meta, err.partial, False, None)
            return self._fail(err, meta["text"], meta["route"])
        self._answer(meta, reply.text, reply.complete, reply.session_id, reply.provider)

    def _answer(self, meta, raw, complete, session_id, provider=None):
        text, mood, point, act = self._read(raw, meta["text"] if meta["route"] == "conversa" else "")
        if not text:
            return self._fail(AIError("vazia"), meta["text"], meta["route"])
        balloons, cut = prompts.balloons(text)
        if not complete:
            balloons.append(FAIL["incompleta"])
            self.retry_text = meta["text"]
        self.conv.add("ceci", text, route=meta["route"], mood=mood, complete=complete, provider=provider)
        keep = {"last_keys": meta["keys"], "last_module": meta["ctx"]} if meta["keys"] is not None else {}
        if provider:
            keep["provider"] = provider
        self.conv.remember(session_id=session_id, last_topic=meta["route"], personality_key=meta["pkey"], **keep)
        self.changed.emit()
        self.answered.emit({"text": text, "balloons": balloons, "truncated": cut, "mood": mood,
                            "anim": self._anim(mood, meta["ctx"], text), "route": meta["route"], "point": point,
                            "action": act})

    @staticmethod
    def _read(raw, user_text=""):
        """Resposta crua → (texto, humor, ponto, ação). [aponta: X, Y] (0–1000 na tela olhada): o App leva ela até
        lá. [faz: nome] (ou, sem marca, o pedido do usuário que bate com uma ação dela): o App faz de verdade."""
        text, mood = prompts.parse(raw)
        text, act = actions.from_reply(prompts.NOTE.sub("", text), user_text, mood)
        point = None
        m = prompts.POINT.search(text)
        if m:
            point = (min(1000, int(m.group(1))) / 1000, min(1000, int(m.group(2))) / 1000)
            text = prompts.POINT.sub("", text).strip()
        return text, mood, point, act

    def _clock(self):
        return time.strftime("%H:%M:%S", time.localtime(self.now()))

    def _anim(self, mood, ctx, text=""):
        """Animação pela resposta: dados acadêmicos mandam (prazo urgente / atividade), depois a ação de roleplay
        que ela escreveu (*bebe café* → café), senão o humor dela."""
        if ctx and ctx["atividades"] and mood not in ("rindo", "triste", "negando", "confusa"):
            return "prazo" if any(a.get("urgente") for a in ctx["atividades"]) else "tarefa"
        return prompts.action_anim(text) or prompts.MOODS[mood]

    def _fail(self, err, text, route):
        self.watchdog.stop()
        self.busy = None
        if err.kind != "cancelada":
            self.retry_text = text  # a mensagem original fica guardada para "tenta de novo"
        say = FAIL[err.kind]
        self.conv.add("ceci", say, route=route, error=err.kind)
        self.changed.emit()
        self.failed.emit({"kind": err.kind, "say": [say], "detail": str(err),
                          "anim": "confusa" if err.kind == "indisponivel" else "negando"
                          if err.kind == "cancelada" else "erro",
                          # pediu uma ação dela e a IA falhou: ela faz mesmo assim (é animação, não precisa de IA)
                          "action": actions.wanted(text) if route == "conversa" and err.kind != "cancelada" else None})

    def _local_answer(self, r):
        kind = academic.intent(r.rest)
        lines = texts.answer(self.store, kind, self.now())
        self.conv.add("ceci", "\n".join(lines), route="local")
        self.changed.emit()
        self.speak.emit("prazo" if kind == "atrasadas" else "tarefa", lines)

    def _say(self, anim, lines):
        self.conv.add("ceci", "\n".join(lines), route="local")
        self.changed.emit()
        self.speak.emit(anim, lines)

    # --- tela ---
    def look(self, image, question="", where=""):
        """Ela olha um print tirado agora (Ctrl+Alt+C ou "olha minha tela"): só esse pedido leva a imagem, e o
        que ela responder fica marcado como tela (vira "print velho" no contexto das próximas)."""
        q = question or "Olha minha tela e comenta o que tá rolando aí."
        self.conv.add("user", "🖥️ " + q, route="tela", window=where)
        self.changed.emit()
        self.state.emit("atencao")
        self.ask(q, router.Route("tela", "", q), logged=True, image=image, where=where)

    def peek(self, image, where, provider=None):
        """Espiada sozinha (você trocou de aba no navegador): comentário curto sem travar a conversa. Falha,
        limite ou "[nada]" ficam quietos; mensagem sua no meio do caminho descarta a espiada."""
        if self.busy or self.peeking:
            return False
        try:
            system = self.persona.instructions() + f"\n\nAGORA (data e hora do PC): {live.now_text(self.now())}"
        except OSError:
            return False
        prompt = prompts.build(system, self.conv.recent(8, 300, new_shot=True),
                               prompts.PEEK.format(where=where, when=self._clock()))
        prompt.image = image
        provider, job = provider or self.provider, self.job
        self.peeking = True

        def work():
            try:
                r = provider.send_message(prompt, 40)
                self._peeked.emit((job, where, r.text, r.provider))
            except Exception:  # limite, rede, sem IA que enxerga: espiada é opcional, fica quieta
                self._peeked.emit((job, where, None, None))
        threading.Thread(target=work, daemon=True).start()
        return True

    def _peek_done(self, res):
        job, where, raw, provider = res
        self.peeking = False
        if not (raw or "").strip() or job != self.job or self.busy or prompts.NOTHING.match(raw):
            return
        text, mood, point, act = self._read(raw)
        if not text or prompts.NOTHING.match(text):
            return
        balloons, cut = prompts.balloons(text)
        self.conv.add("ceci", text, route="tela", auto=True, window=where, mood=mood, provider=provider)
        self.changed.emit()
        self.answered.emit({"text": text, "balloons": balloons[:2], "truncated": cut, "mood": mood,
                            "anim": self._anim(mood, None, text), "route": "tela", "point": point, "auto": True,
                            "action": act})

    # --- arquivos ---
    def attach(self, path, question=None):
        """Arquivo .txt/.md que o usuário entregou (arrastado nela ou "Anexar" no chat): lê e manda pra IA."""
        name = os.path.basename(path)
        try:
            text = files.read(path)
        except ValueError as e:
            if str(e) == "tipo":
                return self._say("negando", [f"Só leio .txt e .md por enquanto. Esse \"{name}\" eu não abro."])
            return self._say("negando", [f"Esse \"{name}\" é grande demais pra mim, porra. Até 50 MB."])
        except OSError:
            return self._say("confusa", [f"Não consegui abrir o \"{name}\"."])
        if not text:
            return self._say("confusa", [f"O \"{name}\" tá vazio. Cê me mandou um nada, KKKKK."])
        self.files[path] = text
        self.conv.remember(file={"name": name, "path": path, "size": len(text)})
        self.conv.add("user", f"📄 {name}", route="arquivo", file=name)
        self.changed.emit()
        q = question or "Lê esse arquivo que eu te mandei e me fala o que achou: do que se trata e o que chama atenção."
        self.state.emit("atencao")
        self.fresh_file = True
        self.ask(q, router.Route("conversa", "", q))

    def _file_text(self, f):
        """Texto inteiro do arquivo da conversa (memória; relido do disco depois de reabrir a Ceci)."""
        path = f.get("path")
        if path and path not in self.files:
            try:
                self.files[path] = files.read(path)
            except (OSError, ValueError):
                return f.get("text")  # histórico antigo guardava o texto
        return self.files.get(path) or f.get("text")

    # --- controle ---
    def cancel(self):
        if not self.busy:
            return self._say(None, ["Não tô esperando resposta nenhuma agora."])
        self.provider.cancel()
        text = self.busy
        self.job += 1  # a resposta que ainda chegar é descartada
        self._fail(AIError("cancelada"), text, "conversa")

    def _expired(self):
        if self.busy:
            self.provider.cancel()
            self.job += 1
            self._fail(AIError("timeout"), self.busy, "conversa")

    def retry(self):
        if self.busy:
            return self._say(None, ["Ainda tô esperando a anterior."])
        if not self.retry_text:
            return self._say(None, ["Não tem nada pra tentar de novo."])
        text, self.retry_text = self.retry_text, None
        self.state.emit("atencao")
        self.ask(text, self._route(text), logged=True)

    def reset(self):
        """Nova conversa: o provedor esquece, o contexto zera, o histórico continua na janela do chat."""
        if self.busy:
            self.provider.cancel()
            self.job += 1
            self.busy = None
            self.watchdog.stop()
        self.provider.reset_session()
        self.conv.new_session()
        self.changed.emit()

    def close(self):
        if self.busy:
            self.provider.cancel()
        self.provider.close()
