"""Fase 2 no app inteiro: a Ceci reage à consulta com as animações e falas certas (servidor falso local).

Uso: python tests/sala_app_test.py
"""
import os
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["CECI_CONFIG_DIR"] = tempfile.mkdtemp(prefix="cecibot_salaapp_")  # nunca as do usuário
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import time  # noqa: E402

from PySide6.QtCore import QCoreApplication, QEventLoop, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import main as M  # noqa: E402
M.fullscreen_app_active = lambda: False  # tela cheia de verdade no PC (vídeo, jogo) não entra no teste
from ceci.sala import protect  # noqa: E402
from ceci.tray import build_menu  # noqa: E402
from fake_moodle import SESSION, Fake, serve  # noqa: E402

qa = QApplication(sys.argv)
fails = []


def check(name, cond):
    print(("ok   " if cond else "FALHA"), name)
    if not cond:
        fails.append(name)


fake = Fake(time.time())
srv = serve(fake)
protect.save({"base": fake.base, "cookies": [{"name": "MoodleSession", "value": SESSION, "domain": "127.0.0.1",
                                              "path": "/"}], "ua": "teste", "ical": None})
app = M.App(qa)
app.s["follow_mouse"] = False
app.sala.store.set_prefs(url=fake.base, quiet=False)
w = app.win
w.set_start_pos()
w.show()
w.play("idle", force=True)
played, said = [], []
orig_play = w.play
w.play = lambda aid, **kw: (played.append(aid), orig_play(aid, **kw))[1]
orig_say = app.speech.say
app.speech.say = lambda cat, prio=1, force=False, text=None: (said.append((cat, text)),
                                                              orig_say(cat, prio, force, text))[1]


def check_now():
    loop = QEventLoop()
    app.sala.finished.connect(loop.quit)
    app.check_sala()
    QTimer.singleShot(60000, loop.quit)
    loop.exec()
    app.sala.finished.disconnect(loop.quit)
    for _ in range(5):
        QCoreApplication.processEvents()


menu = build_menu(app)
labels = [a.text() for a in menu.actions()]
check("menu tem Minhas atividades, Resumo e Conferir agora",
      {"Minhas atividades", "Resumo da faculdade", "Conferir Sala Virtual agora"} <= set(labels))

check_now()
check("início da consulta = Conferindo Sala Virtual; depois Atualizando dados; fim = Sucesso",
      played[:3] == ["sala_virtual", "atualizando", "sucesso"])
check("fala de consulta concluída (só quando deu certo)", ("sv_ok", None) in said)
check("primeira sincronização: Resumo do dia + ela fala o que vence na semana (sem janela)",
      "resumo" in played and any(t and "faltam" in t for _, t in said + [(c, t) for c, _, t in app.speech.queue]))
check("resumo diz quantas atividades achou", any(t and t.startswith("Encontrei ") for _, t in said))

played.clear()
said.clear()
fake.acts[520] = {"course": 101, "mod": "assign", "name": "Lista 4", "due": time.time() + 15 * 86400, "status": "new"}
check_now()
check("atividade nova = Mostrando tarefa + fala de nova + título e prazo no balão",
      "tarefa" in played and ("sv_nova", None) in said and any(t and "Lista 4" in t for _, t in said))

played.clear()
said.clear()
fake.valid = set()
check_now()
check("sessão expirada = animação de erro + 'não consegui entrar' (nada de 'conferi tudo')",
      "erro" in played and ("sv_falha_login", None) in said and ("sv_ok", None) not in said)
fake.valid = {SESSION}

played.clear()
said.clear()
app.set_paused(True)
fake.acts[521] = {"course": 101, "mod": "assign", "name": "Lista 5", "due": time.time() + 15 * 86400, "status": "new"}
check_now()
check("pausada: consulta acontece, mas a Ceci não anima nem fala", not played and not said
      and "cm:521" in {r["key"] for r in app.sala.store.rows()})
app.set_paused(False)

app.speech.say("idle", 3, force=True)
app.speech.say("curiosa", 3, force=True)
said.clear()
app.command("o que vence essa semana?")
check("caixinha: pergunta da semana = ela fala as atividades", any(t and "vencendo" in t for _, t in said))
check("caixinha tem prioridade: corta o que ela falava e responde na hora",
      "vencendo" in app.speech.bubble.text and "curiosa" not in [q[0] for q in app.speech.queue])
app.speech.bubble.stop()
app.speech.queue = []
said.clear()
app.command("qual a capital da frança")
check("caixinha: conversa sem IA conectada, ela diz (não inventa)", any(t and "não tenho uma IA" in t for _, t in said))
app.ask()
QCoreApplication.processEvents()
check("clique duplo abre a caixinha", app.box is not None and app.box.isVisible())
app.box.close()
app.open_sala()
QCoreApplication.processEvents()
check("Configurações da Sala Virtual abre", app.sala_dlg.isVisible())

srv.shutdown()
print(f"\n{len(fails)} falha(s)" if fails else "\ntudo ok")
sys.exit(1 if fails else 0)
