"""Configurações: o tamanho escolhido (no diálogo ou no menu) continua o mesmo ao abrir de novo.

Uso: python tests/settings_test.py
"""
import os
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["CECI_CONFIG_DIR"] = tempfile.mkdtemp(prefix="cecibot_test_")  # nunca as do usuário
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtWidgets import QApplication  # noqa: E402

import main as M  # noqa: E402
M.fullscreen_app_active = lambda: False  # tela cheia de verdade no PC (vídeo, jogo) não entra no teste
from ceci.settings import PATH, Settings  # noqa: E402
from ceci.ui import SettingsDialog  # noqa: E402

qa = QApplication(sys.argv)
fails = []


def check(name, cond):
    print(("ok   " if cond else "FALHA"), name)
    if not cond:
        fails.append(name)


app = M.App(qa)
dlg = SettingsDialog(app.s, app._apply)
dlg.size.setValue(0.7)
dlg.apply()
check("diálogo grava o tamanho no arquivo", Settings()["size"] == 0.7)
check("e aplica na hora", app.win.sprites.scale == 0.7)
app.win.save_pos()  # outras gravações (posição) não voltam o tamanho
check("gravar a posição não mexe no tamanho", Settings()["size"] == 0.7)
app2 = M.App(qa)
check("ao abrir de novo começa no tamanho salvo", app2.win.sprites.scale == 0.7)
app2.set_size(0.4)
check("menu Alterar tamanho também fica salvo", M.App(qa).win.sprites.scale == 0.4)
check("arquivo em CECI_CONFIG_DIR (teste não toca no do usuário)", PATH.startswith(os.environ["CECI_CONFIG_DIR"]))
sys.exit(1 if fails else 0)
