"""Ceci Bot — mascote interativa para a área de trabalho (Fase 2: avisos da Sala Virtual)."""
import ctypes
import os
import random
import sys
import time

from PySide6.QtCore import QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QSystemTrayIcon

from ceci import desktop, shared
from ceci.page import Page
from ceci.behavior import Behavior
from ceci.command import HELP, CommandBox
from ceci.ia import actions, make_provider, prompts, screen
from ceci.hotkey import Hotkey
from ceci.ia.live import Mind
from ceci.ia.assistant import Assistant
from ceci.ia.chat import ChatWindow
from ceci.sala import texts
from ceci.sala.service import SalaVirtual
from ceci.sala.store import deadline, status
from ceci.sala.ui import SalaDialog, open_url
from ceci.settings import ROOT, Settings
from ceci.speech import Speech
from ceci.tray import Tray, build_menu
from ceci.ui import AnimPanel, SettingsDialog
from ceci.watch import Watcher
from ceci.window import CeciWindow

ICON = os.path.join(ROOT, "assets", "icon", "ceci.png")


def fullscreen_app_active():
    """Janela em primeiro plano cobre o monitor inteiro (jogo/vídeo)? Só usa APIs do Windows."""
    if sys.platform != "win32":
        return False
    u = ctypes.windll.user32
    hwnd = u.GetForegroundWindow()
    if not hwnd:
        return False
    cls = ctypes.create_unicode_buffer(64)
    u.GetClassNameW(hwnd, cls, 64)
    if cls.value in ("Progman", "WorkerW", "Shell_TrayWnd"):
        return False

    class RECT(ctypes.Structure):
        _fields_ = [("l", ctypes.c_long), ("t", ctypes.c_long), ("r", ctypes.c_long), ("b", ctypes.c_long)]

    class MI(ctypes.Structure):
        _fields_ = [("cb", ctypes.c_ulong), ("mon", RECT), ("work", RECT), ("flags", ctypes.c_ulong)]
    r = RECT()
    u.GetWindowRect(hwnd, ctypes.byref(r))
    mi = MI(cb=ctypes.sizeof(MI))
    u.GetMonitorInfoW(u.MonitorFromWindow(hwnd, 2), ctypes.byref(mi))
    m = mi.mon
    return r.l <= m.l and r.t <= m.t and r.r >= m.r and r.b >= m.b


class App:
    def __init__(self, qapp):
        self.qapp = qapp
        self.s = Settings()
        self.win = CeciWindow(self.s)
        self.beh = Behavior(self.win, self.s)
        self.speech = Speech(self.win, self.s)
        self.hold = None  # animação de cena segurada enquanto a resposta é falada
        self.speech.bubble.ended.connect(self._release_hold)
        self.win.context_menu.connect(self._menu)
        self.win.double_clicked.connect(self.ask)
        self.win.files_dropped.connect(self.drop_files)
        self.sala = SalaVirtual(is_fullscreen=fullscreen_app_active)
        self.sala.progress.connect(self._sala_progress)
        self.sala.finished.connect(self._sala_finished)
        self.sala.alerts.connect(self._sala_alerts)
        self.ai = Assistant(make_provider(self.s["ai_provider"], self.s["ai_chain"]), self.sala.store, self.s, clock=self.sala.now)
        self.ai.state.connect(self._ai_state)
        self.ai.answered.connect(self._answered)
        self.ai.failed.connect(lambda f: self._act(f["action"], f["say"]) if f.get("action")
                               else self._say(f["anim"], f["say"]))
        self.ai.speak.connect(self._say)
        self.ai.local.connect(self.run_local)
        self.shot = self.screen_geom = None
        self.shot_where = ""  # título da janela da frente quando o print foi tirado
        self.hotkey = Hotkey(qapp)
        self.hotkey.pressed.connect(self.look_screen)
        self._log_start()
        # cérebro: falas soltas e vontades vindas da IA (outra corrente, mesmas pausas de limite)
        mp = make_provider(self.s["ai_provider"], self.s["ai_chain"])
        if hasattr(mp, "paused") and hasattr(self.ai.provider, "paused"):
            mp.paused = self.ai.provider.paused
        wants = [a for a, d in self.win.sprites.anims.items() if d.get("auto")]
        self.mind = Mind(mp, self.ai.persona, self.ai.conv, self.sala.store, self.s, wants)
        self.speech.live = self.mind
        self.beh.mind = self.mind
        self.ai.answered.connect(lambda a: self.mind.maybe_refresh(after_chat=True))
        self.peeker = mp  # espiada sozinha usa a corrente do cérebro: não disputa com a conversa
        self.watch = Watcher()
        self.watch.tab.connect(self._peek)
        self.page = self.win.page = Page()  # botões, imagens... da página do navegador: ela senta neles
        self.page.set_on(self.s["perch"])
        self.page_timer = QTimer(interval=500, timeout=self._page_target)
        self.page_timer.start()
        self.tray = Tray(self, ICON)
        self.tray.messageClicked.connect(self._toast_clicked)
        self.toast_url, self.toast_action = None, self.tell_activities
        self.panel = self.dlg = self.sala_dlg = self.box = self.chat_win = None
        self.fs_paused = False
        self.fs_timer = QTimer(timeout=self._check_fullscreen)
        self._update_fs_timer()

    def _log_start(self):
        """Diagnóstico ao abrir (sem nenhuma chave): pasta usada, serviços com chave, mensagens no histórico."""
        from ceci.ia import keys
        from ceci.settings import CONFIG_DIR, SHARED_DIR
        try:
            with open(os.path.join(CONFIG_DIR, "ceci.log"), "a", encoding="utf8") as f:
                f.write(f"{time.strftime('%d/%m %H:%M:%S')} abriu | pasta {CONFIG_DIR} | chaves {sorted(keys.load())} | "
                        f"mensagens {len(self.ai.conv.messages)} | IA {self.ai.provider.is_available()} | "
                        f"Ctrl+Alt+C {'ok' if self.hotkey.ok else 'ocupado por outro programa'} | "
                        f"personalidade em {SHARED_DIR}\n")
        except OSError:
            pass
        QTimer.singleShot(15000, self._log_page)

    def _log_page(self):
        """Diagnóstico da leitura da página (só se funcionou e quantos itens; nunca os nomes)."""
        from ceci.settings import CONFIG_DIR
        p = self.page
        try:
            with open(os.path.join(CONFIG_DIR, "ceci.log"), "a", encoding="utf8") as f:
                f.write(f"{time.strftime('%d/%m %H:%M:%S')} página | ligada {p.on} | "
                        f"{'erro ' + p.error if p.error else 'ok'} | itens {len(p.items)}\n")
        except OSError:
            pass

    def start(self):
        self.win.set_start_pos()
        self.win.show()
        if self.s["door_entrance"]:
            self.win.play("entrada", force=True, talk=True)  # não aparece parada antes da entrada
        else:
            self.win.play("idle", force=True)  # abre direto no idle novo (folha idle.png)
            self.beh.schedule()
            QTimer.singleShot(700, lambda: self.speech.say("inicio", 3, force=True))
        self.speech.restart_chat()
        self.win.update_eye_timer()
        self.win.update_breath()
        self.mind.start()
        self.watch.set_on(self.s["auto_look"])
        self.sala.start()  # consulta do dia pendente (se houver) e lembretes: depois que ela entra na tela

    # --- menu ---
    def _menu(self, pos):
        self.beh.user_activity()
        self._ctx = build_menu(self)
        self._ctx.popup(pos)

    def interact(self):
        self.beh.user_activity()
        self.win.interact(talk=True)

    def chat(self):
        self.beh.user_activity()
        self.speech.say(random.choice(["idle", "curiosa", "conversando", "raras"]), 3, force=True)

    def stroll(self):
        """Caminha até um ponto aleatório da tela ou da janela onde está (sentido oposto se estiver perto da borda)."""
        self.beh.user_activity()
        w = self.win
        left, right = w.span()
        d = random.uniform(180, 420) * w.sprites.scale / 0.55
        x = w.foot.x() + (d if w.foot.x() < (left + right) / 2 else -d)
        w.walk_to(x)

    def set_perch(self, on):
        """Menu "Sentar nas janelas": desligando com ela lá em cima, ela pula para o chão."""
        self.s["perch"] = bool(on)
        self.s.save()
        self.page.set_on(on)
        if not on and self.win.perch:
            self.win.jump_to(None, self.win.foot.x())

    def _page_target(self):
        """Diz à leitura da página qual é o navegador da frente (desktop.foreground só roda na thread da tela)."""
        if not (self.page.on and self.win.isVisible() and not self.fs_paused):
            self.page.fg = None
            return
        fg = desktop.foreground()
        if fg is None:  # a própria Ceci (arrastando, chat) ou a área de trabalho: continua lendo o navegador de antes
            if self.page.fg and desktop.rect_of(self.page.fg) is None:
                self.page.fg = None  # fechou ou minimizou
            return
        self.page.fg = fg.hwnd if fg.browser else None

    def set_auto_look(self, on):
        """Menu "Espiar a tela sozinha"."""
        self.s["auto_look"] = bool(on)
        self.s.save()
        self.watch.set_on(bool(on))

    def open_panel(self):
        if not self.panel:
            self.panel = AnimPanel(self.win, self.beh)
        self.panel.show()
        self.panel.raise_()

    def open_settings(self):
        label = "Sala Virtual (conectada)…" if self.sala.connected() else "Conectar Sala Virtual"
        self.dlg = SettingsDialog(self.s, self._apply, sala=(label, self.open_sala))
        self.dlg.show()

    # --- Sala Virtual ---
    def _open(self, attr, make):
        w = getattr(self, attr) or make()
        setattr(self, attr, w)
        w.showNormal()
        w.raise_()
        w.activateWindow()

    def open_sala(self):
        self._open("sala_dlg", lambda: SalaDialog(self.sala))

    def tell(self, what, aid="tarefa"):
        """Ela responde falando (sem janela), com os dados da última consulta."""
        self._say(aid, texts.answer(self.sala.store, what, self.sala.now()))

    def tell_activities(self):
        self.tell("atividades")

    def tell_summary(self):
        self.tell("resumo", "resumo")

    def _say(self, aid, lines):
        w = self.win
        if not w.isVisible() or w.player.paused or w.exiting:
            return
        self.beh.user_activity()
        if aid and not w.dragging:
            w.stop_walk()
            self.speech.muted = aid  # a fala é a resposta, não a automática da animação
            # cena com trecho que repete (café, livro, gato...): segura enquanto ela fala, sem passar correndo
            loop = w.sprites.anims.get(aid, {}).get("loop")
            w.play(aid, force=True, **({"loops": "inf"} if loop else {}))
            self.hold = aid if loop else None
        self.speech.say_many(lines)

    def _release_hold(self):
        """Terminou de falar: a cena que estava segurando sai pelo fim dela e volta pro idle."""
        if self.hold and not self.speech.queue and not self.speech.bubble.typing():
            if self.win.player.aid == self.hold and not self.win.exiting:
                self.win.play("idle", force=True)
            self.hold = None

    # --- caixinha do clique duplo ---
    def ask(self):
        if self.box:
            self.box.close()
        box = self.box = CommandBox()
        box.submitted.connect(self.command)
        box.destroyed.connect(lambda *_: self.box is box and setattr(self, "box", None))
        box.show_beside(self.win.foot, self.win.sprites.scale, self.win.area())

    def _answered(self, a):
        if a.get("auto"):  # espiada sozinha (trocou de janela/aba): só comenta, sem andar até o ponto nem fazer nada
            return self._say(a["anim"], a["balloons"])
        if a.get("point") and a.get("route") == "tela" and self.screen_geom is not None:
            return self._point(a["point"], a["balloons"])
        if a.get("action"):
            return self._act(a["action"], a["balloons"])
        self._say(a["anim"], a["balloons"])

    def _act(self, action, lines):
        """Pedido que bate com uma ação dela (ceci/ia/actions.py): fala e faz de verdade, com a animação ou o
        movimento que já existe. A cena segue o tempo dela (não para quando a fala acaba)."""
        w = self.win
        aid = actions.ACTIONS[action][1]
        if not w.isVisible() or w.player.paused or w.exiting or w.dragging or w.fall_v is not None:
            return self._say(None, lines)
        self.beh.user_activity()
        lines = list(lines)
        if aid == "_subir":
            if w.perch:
                lines.append("(Já tô em cima de uma janela, porra.)")
            elif not self.s["perch"] or not w.climb():
                lines.append("(Não tem janela com a borda livre pra eu subir agora.)" if self.s["perch"]
                             else "(\"Sentar nas janelas\" tá desligado no menu.)")
        elif aid == "_descer":
            if w.perch:
                w.jump_to(None, w.foot.x())
        elif aid == "_passear":
            self.stroll()
        elif aid == "_acordar":
            w.wake()
        else:
            w.stop_walk()
            self.speech.muted = aid  # a fala é a resposta, não a automática da animação
            self.hold = None
            if w.sprites.anims[aid].get("edge") and w.perch:  # esconder na parede: desce da janela antes
                w.jump_to(None, w.foot.x(), then=lambda: w.play(aid, force=True))
            else:
                w.play(aid, force=True)
        self.speech.say_many(lines)

    def _point(self, pt, lines):
        """Resposta sobre a tela com [aponta]: anda até embaixo da coisa (no chão ou na borda da janela onde
        está) e aponta enquanto fala."""
        w, g = self.win, self.screen_geom
        x = g.left() + pt[0] * g.width()
        if not w.isVisible() or w.player.paused or w.exiting or w.dragging or w.fall_v is not None:
            return self._say(None, lines)
        s = w.sprites.scale
        x = w.clamp_x(x, 90 * s)
        self.speech.say_many(lines)
        if abs(x - w.foot.x()) < 40 * s:
            self.speech.muted = "apontando"
            return w.play("apontando", force=True)
        w.walk_to(x, on_done=lambda: (setattr(self.speech, "muted", "apontando"), w.play("apontando", force=True)))

    def look_screen(self):
        """Ctrl+Alt+C: print da tela (antes da caixinha aparecer) e caixinha pra perguntar; Enter vazio = comenta."""
        if self.win.exiting:
            return
        self.beh.user_activity()
        fg = desktop.foreground()
        self.shot_where = fg.title if fg else ""
        self.shot, self.screen_geom = screen.grab()
        if self.box:
            self.box.close()
        box = self.box = CommandBox()
        box.allow_empty = True
        box.setPlaceholderText("pergunta da tela (Enter = ela comenta)")
        box.submitted.connect(self._screen_message)
        box.destroyed.connect(lambda *_: self.box is box and setattr(self, "box", None))
        box.show_beside(self.win.foot, self.win.sprites.scale, self.win.area())
        self.speech.say("sv_info", 3, force=True, text="Pergunta da tela ou Enter vazio que eu comento.")

    def _screen_message(self, text):
        """Caixinha do Ctrl+Alt+C: Enter vazio ou pergunta sobre a tela leva o print; o resto é conversa normal."""
        n = texts.norm(text)
        if not text or prompts.ABOUT_SCREEN.search(n) or prompts.SCREEN_ASK.search(n):
            return self.ai.look(self.shot, text, self.shot_where)
        self.shot = None
        self.command(text)

    def _look_now(self, text):
        """Mensagem que pede pra ela olhar a tela ("olha isso aqui", "tá vendo esse erro?"): print tirado agora,
        nunca a descrição de um print antigo."""
        fg = desktop.foreground()
        shot, self.screen_geom = screen.grab()
        self.ai.look(shot, text, fg.title if fg else "")

    def _peek(self, w):
        """Você ficou numa janela ou aba nova: ela olha e solta um comentário curto (se estiver à vista e
        ninguém estiver falando com ela)."""
        if (not self.s["auto_look"] or not self._can_react() or self.box or self.ai.busy or self.ai.peeking
                or self.speech.bubble.active() or self.win.fall_v is not None):
            return
        shot, geom = screen.grab(w.rect.center())
        where = f'a aba "{w.title}" no navegador' if w.browser else \
            f'a janela "{w.title}" ({w.exe.removesuffix(".exe") or "um programa"})'
        if self.ai.peek(shot, where, self.peeker):
            self.screen_geom = geom
            self._ai_anim("observando")

    def drop_files(self, paths):
        """Arquivo solto em cima dela: ela lê (só .txt e .md) e comenta."""
        self.beh.user_activity()
        self.speech.cut()
        self.ai.attach(paths[0])

    def command(self, text):
        self.speech.cut()  # o que você digitou tem prioridade sobre o que ela estava falando
        if not self.ai.busy and prompts.SCREEN_ASK.search(texts.norm(text)):
            # pede pra olhar a tela: print na hora (depois que a caixinha some), nada de print velho
            return QTimer.singleShot(150, lambda: self._look_now(text))
        self.ai.handle(text)  # roteador: comando local, pergunta com dados da Sala Virtual ou conversa

    def _ai_state(self, st):
        """Mensagem recebida → Observando; esperando a IA → Pensando e, se demorar, Processando."""
        if st == "pensando":  # deixa ver ela prestando atenção antes de começar a pensar
            return QTimer.singleShot(700, lambda: self.ai.busy and self._ai_anim("pensando"))
        self._ai_anim("observando" if st == "atencao" else "processando")

    def _ai_anim(self, aid):
        w = self.win
        if w.isVisible() and not w.player.paused and not w.exiting and not w.dragging:
            w.stop_walk()
            self.speech.muted = aid  # nada de fala automática da animação no meio da conversa
            w.play(aid, force=True, **({} if aid == "observando" else {"loops": "inf"}))

    def open_chat(self):
        self._open("chat_win", lambda: ChatWindow(self.ai, self.command))

    def run_local(self, action, rest):
        """Comandos registrados (o roteador só manda frase que bate inteira com o padrão)."""
        now = self.sala.now()
        if action in ("atividades", "prazo", "hoje", "amanha", "semana", "atrasadas"):
            self.tell(action, "prazo" if action == "atrasadas" else "tarefa")
        elif action == "resumo":
            self.tell_summary()
        elif action in ("fiz", "desfazer"):
            self._mark(rest, action == "fiz", now)
        elif action == "conferir":
            self.check_sala()
        elif action == "conectar":
            self.open_sala()
        elif action == "passear":
            self.stroll()
        elif action == "falar":
            self.chat()
        elif action == "esconder":
            self.hide_ceci()
        elif action == "configuracoes":
            self.open_settings()
        elif action == "chat":
            self.open_chat()
        elif action == "quieta":
            self.speech.last_auto = time.monotonic() + 1800  # sem falas automáticas por meia hora
            self._say(None, ["Tá bom, fico quietinha por meia hora."])
        elif action == "dormir":
            self.win.stop_walk()
            self.win.play("cochilo", force=True)
        elif action == "acordar":
            self.win.wake()
        elif action == "abrir_atividade":
            self._open_activity(rest, now)
        elif action == "ajuda":
            self._say(None, HELP)

    def _open_activity(self, rest, now):
        rows = [dict(r) for r in self.sala.store.rows()
                if status(r, now) in ("pendente", "desconhecido", "atrasada") and r["url"]]
        q = texts.norm(rest)
        found = ([r for r in rows if q and q in texts.norm(texts.spoken_course(r))]
                 or [r for r in rows if q and q in texts.norm(r["name"])])
        if len(found) == 1:
            open_url(found[0]["url"])  # abre no seu navegador, com a sua sessão do Moodle
            self._say("tarefa", [f"Abrindo \"{texts.name(found[0], 50)}\" no navegador."])
        elif not found:
            self._say("confusa", [f"Não achei atividade a fazer de \"{rest[:40]}\"."])
        else:
            found.sort(key=lambda r: deadline(r) or 9e12)
            self._say(None, [f"Tem {len(found)}: " + "; ".join(texts.name(r, 40) for r in found[:4])
                             + ". Fala um pedaço do nome (\"abre a atividade de\" + nome)."])

    def _mark(self, rest, on, now):
        if not rest:
            return self._say(None, ["Fiz qual? Digita \"fiz\" e um pedaço do nome da atividade."])
        found = texts.find(self.sala.store, rest, now, done=not on)
        if len(found) == 1:
            r = found[0]
            self.sala.store.set_manual(r["key"], on, now)
            self.sala.reschedule()
            msg = (f"Marquei \"{texts.name(r, 50)}\" como feita por você. Não é entrega confirmada no Moodle, viu?"
                   if on else f"Desmarquei \"{texts.name(r, 50)}\". Volto a cobrar.")
            self._say("feliz" if on else None, [msg])
        elif not found:
            self._say("confusa", [f"Não achei nenhuma atividade {'a fazer' if on else 'marcada por você'} com "
                                  f"\"{rest[:40]}\" no nome."])
        else:
            self._say(None, [f"Achei {len(found)}: " + "; ".join(texts.name(r, 40) for r in found[:4])
                             + ". Digita um pedaço maior do nome."])

    def check_sala(self):
        if not self.sala.connected():
            self.open_sala()
        elif not self.sala.sync("manual"):
            self.speech.say("sv_info", 3, force=True, text="Calma, já tô conferindo a Sala Virtual!")

    def _can_react(self, eco_skip=False):
        """A Ceci só reage quando está à vista, sem pausa e sem tela cheia (no econômico, só o essencial)."""
        w = self.win
        return (self.sala.store.prefs()["ceci"] and w.isVisible() and not w.player.paused and not w.exiting
                and not w.dragging and not self.fs_paused and not (eco_skip and self.s["eco"]))

    def _react(self, aid, cat=None, text=None, eco_skip=False):
        if not self._can_react(eco_skip):
            return
        self.win.stop_walk()
        self.speech.muted = aid  # a fala vem daqui (o resultado real), não a automática da animação
        self.win.play(aid, force=True)
        if cat:
            self.speech.say(cat, 3, force=True)
        if text:
            self.speech.say("sv_info", 3, force=True, text=text)

    def _sala_progress(self, stage):
        self._react("sala_virtual" if stage == "conferindo" else "atualizando", eco_skip=True)

    def _sala_finished(self, out):
        r, k = out["result"], out["kind"]
        if r == "desconectada":
            if out["trigger"] == "manual":
                self.open_sala()
            return
        if r == "ok":
            self._react("sucesso", "sv_ok")
        elif k == "sessao":
            self._react("erro", "sv_falha_login",
                        "Conferi só os prazos pelo calendário; os envios ficam pra quando você entrar de novo."
                        if r == "parcial" else "Preciso que você entre de novo na Sala Virtual.")
        elif r == "parcial":
            self._react("confusa", "sv_parcial", out["message"])
        elif k == "sem_internet":
            self._react("confusa", "sv_sem_internet")
        else:
            self._react("erro", "sv_falha")
        if r != "ok" and (out["trigger"] == "auto" or not self._can_react()) and self.sala.store.prefs()["toast"]:
            self.toast_url = None
            self.toast_action = self.open_sala if k == "sessao" else self.tell_activities
            self.tray.showMessage("Sala Virtual · consulta " + ("parcial" if r == "parcial" else "falhou"),
                                  out["message"] + ("\nClique para entrar de novo." if k == "sessao" else ""),
                                  QSystemTrayIcon.Warning, 15000)

    def _sala_alerts(self, a):
        """Ela fala os avisos, um atrás do outro. Notificação do Windows só quando ela não pode falar."""
        items, now, prefs = a["items"], a["now"], self.sala.store.prefs()
        can = not a["fullscreen"] and self._can_react()
        if a["first"]:  # primeira sincronização: um resumo em vez de uma enxurrada de avisos
            rows = [dict(r) for r in self.sala.store.rows()]
            soon = sorted((r for r in rows if status(r, now) in ("pendente", "desconhecido", "evento")
                           and now <= (deadline(r) or 0) < now + 7 * 86400), key=deadline)
            lines = [f"Encontrei {len(rows)} atividades em {len({r['course'] for r in rows})} disciplinas; "
                     f"{len(soon)} vencem nos próximos 7 dias."] + [texts.line(r, now) for r in soon[:5]]
            if can:
                return self._say("resumo", lines + ([f"E mais {len(soon) - 5}."] if len(soon) > 5 else []))
            items = items or [{"row": r, "tier": "3d"} for r in soon]
        if not items:
            return
        if not can:
            if prefs["toast"]:  # pausada, oculta ou tela cheia: não perde o aviso
                t, body = texts.toast(items, now)
                self.toast_url = items[0]["row"]["url"] if len(items) == 1 else None
                self.toast_action = self.tell_activities
                self.tray.showMessage(t, body, QSystemTrayIcon.Information, 15000)
            return
        if len(items) == 1:
            i = items[0]
            aid = {"nova": "tarefa", "prazo_alterado": "tarefa", "entregue": "feliz", "7d": "lembrete",
                   "3d": "lembrete"}.get(i["tier"], "prazo")
            self._react(aid, texts.speech_category(i, now), texts.speech_line(i, now))
        else:
            lines = [f"Tenho {len(items)} avisos da faculdade:"] + [texts.speech_line(i, now) for i in items[:6]]
            self._say("resumo", lines + ([f"E mais {len(items) - 6}."] if len(items) > 6 else []))

    def _toast_clicked(self):
        if self.toast_url:
            open_url(self.toast_url)
        else:
            self.toast_action()

    def _apply(self):
        self.win.apply_settings()
        self.speech.apply_settings()
        self._update_fs_timer()

    def set_size(self, v):
        self.s["size"] = v
        self.s.save()
        self.win.set_size(v)

    # --- visibilidade / pausa ---
    def set_paused(self, on):
        self.win.player.set_paused(on)
        self.win.update_eye_timer()
        self.win.update_breath()
        self.beh.stop() if on else self.beh.schedule()
        self.speech.hide() if on else self.speech.restart_chat()

    def hide_ceci(self):
        self.beh.stop()
        self.speech.hide()
        self.win.suspend(True)
        self.win.hide()
        self.win.update_eye_timer()

    def show_ceci(self):
        self.win.show()
        self.win.suspend(False)
        self.win.update_eye_timer()
        self.win.play("acenando", force=True)
        QTimer.singleShot(400, lambda: self.speech.say("inicio", 3, force=True))

    def _update_fs_timer(self):
        self.fs_timer.start(3000) if self.s["pause_fullscreen"] else self.fs_timer.stop()

    def _check_fullscreen(self):
        fs = fullscreen_app_active()
        if fs and not self.fs_paused and self.win.isVisible():
            self.fs_paused = True
            self.hide_ceci()
        elif not fs and self.fs_paused:
            self.fs_paused = False
            self.show_ceci()

    # --- saída ---
    def quit_animated(self):
        w = self.win
        if not w.isVisible() or w.exiting:
            self.qapp.quit()
            return
        self.beh.stop()
        self.fs_timer.stop()
        self.watch.set_on(False)
        self.page_timer.stop()
        self.page.close()
        self.sala.shutdown()
        self.ai.close()
        self.hotkey.close()
        w.player.set_paused(False)
        w.eyes_off()
        w.save_pos()
        QTimer.singleShot(20000, self.qapp.quit)  # segurança
        a, s = w.area(), w.sprites.scale
        left = w.foot.x() - a.left() < a.right() - w.foot.x()  # canto mais perto
        # ponto de largada: a corrida (quadros 0-2) termina com ela saindo pela borda
        target = a.left() + 250 * s if left else a.right() + 1 - 250 * s

        self.speech.say("saida", 5, force=True)

        def go():
            w.exiting = True
            self.speech.hide()  # o balão some quando ela sai correndo
            w.play("saida", force=True, mirror=left, on_done=self.qapp.quit)

        def ready():  # só corre depois de terminar de falar o tchau
            QTimer.singleShot(self.speech.remaining_ms(), go)
        def walk_out():
            if abs(w.foot.x() - target) > 20:
                w.walk_to(target, on_done=ready, fast=True)  # sempre andando até o canto
            else:
                ready()
        if not (w.perch and w.jump_to(None, w.foot.x(), then=walk_out)):  # em cima de uma janela: desce antes
            walk_out()


def already_running(name="CeciBot.SingleInstance"):
    """Outra Ceci já aberta? Duas por cima uma da outra parecem animação bugada (mutex nomeado do Windows)."""
    if sys.platform != "win32":
        return False
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.CreateMutexW.restype = ctypes.c_void_p
    main.mutex = k.CreateMutexW(None, False, name)  # fica aberto enquanto o app roda
    return ctypes.get_last_error() == 183  # ERROR_ALREADY_EXISTS


def main():
    if already_running():
        return
    if sys.platform == "win32":
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("CeciBot")
    shared.migrate()  # memória (conversa, humor, personalidade) na pasta do OneDrive: igual em todos os PCs
    qapp = QApplication(sys.argv)
    qapp.setQuitOnLastWindowClosed(False)
    qapp.setWindowIcon(QIcon(ICON))
    app = App(qapp)
    app.start()
    sys.exit(qapp.exec())


if __name__ == "__main__":
    main()
