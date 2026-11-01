"""Sentar nos botões, imagens e campos da página do navegador (ceci/page.py), sem precisar de um navegador: a
leitura da página é trocada por uma de mentira e a janela do navegador também.
Sobe no item, segue quando a página rola, cai quando o item some ou outra janela tapa; o filtro de itens.
Precisa da tela de verdade (não roda com QT_QPA_PLATFORM=offscreen). Uso: python tests/page_test.py
"""
import os
import sys
import tempfile
import time

os.environ["CECI_CONFIG_DIR"] = tempfile.mkdtemp(prefix="cecibot_page_")  # nunca as do usuário
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import QCoreApplication, QEventLoop, QPointF, QRect  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from ceci import desktop, page  # noqa: E402
from ceci.settings import Settings  # noqa: E402
from ceci.window import CeciWindow  # noqa: E402

if os.environ.get("QT_QPA_PLATFORM") == "offscreen" or not desktop.ON:
    print("pulado: precisa do Windows com a tela de verdade")
    sys.exit(0)

app = QApplication(sys.argv)
fails = []


def check(name, cond):
    print(("ok   " if cond else "FALHA"), name)
    if not cond:
        fails.append(name)


def wait(cond, ms=5000):
    end = time.monotonic() + ms / 1000
    while not cond() and time.monotonic() < end:
        QCoreApplication.processEvents(QEventLoop.AllEvents, 30)
        time.sleep(0.01)
    return cond()


# --- filtro dos itens (números nativos) ---
I = page.Item
doc = (0, 100, 1000, 800)
got = page.pick([I(1, "botão", "Curtir", 100, 300, 220, 330), I(1, "botão", "x", 10, 300, 40, 330),
                 I(1, "imagem", "", 100, 50, 400, 90), I(1, "link", "corpo", 0, 120, 1000, 700),
                 I(1, "botão", "Curtir", 101, 301, 221, 331), I(1, "campo", "Busca", 300, 795, 600, 820)], doc)
check("filtro: fica o botão largo dentro da página", [i.name for i in got] == ["Curtir"])

# --- navegador e página de mentira ---
H = 4242
area = QRect(0, 0, 0, 0)
fake_items = []


class FakePage(page.Page):
    def __init__(self):
        super().__init__()
        self.on = True
        self.hwnd = H  # última página lida

    def fresh(self, hwnd, age=2.5):
        return hwnd == H

    def surfaces(self, hwnd=None, min_width=60, top_margin=0):
        return [sf for sf in fake_items if hwnd in (None, H)]


above = []
browser = lambda: desktop.Win(H, "Página - Brave", "brave.exe", area, True, True)  # noqa: E731
desktop.foreground = lambda: None  # com a Ceci no mouse, a janela da frente é ela (foreground = None)
desktop.rect_of = lambda h: area if h == H else None
desktop.windows = lambda: above + [browser()]
desktop.surfaces = lambda **kw: []  # nenhuma janela de verdade no caminho

s = Settings()
s.save = lambda: None
s["follow_mouse"] = False
s["size"] = 0.25
win = CeciWindow(s)
win.set_start_pos()
win.show()
win.page = FakePage()
heard = []
win.interaction.connect(heard.append)
a = win.area()
area = QRect(a.left(), a.top(), a.width(), a.height() - 10)
ground = a.bottom() + 1
sc = win.sprites.scale
x = win.foot.x()
y0 = int(ground - 200)


def item(y, el="botão:Curtir:15", w=260):
    return desktop.Surface(H, int(y), int(x - w / 2), int(x + w / 2), "Curtir", el=el)


fake_items[:] = [item(y0)]
check("item da página entra onde dá para pousar", any(sf.el for sf in win._surfaces()))
check("pulo até o botão começa", win.jump_to(fake_items[0], x))
wait(lambda: win.fall_v is None, 4000)
check("pousou em cima do botão", win.perch is not None and win.perch.el == "botão:Curtir:15"
      and abs(win.foot.y() - y0) < 1)
check("a leitura da página passa a seguir esta janela", win.page.track == H)
# a página rola: o botão sobe 60 px → ela vai junto
fake_items[:] = [item(y0 - 60)]
wait(lambda: abs(win.foot.y() - (y0 - 60)) < 1, 2000)
check("página rolou: ela vai junto com o botão", abs(win.foot.y() - (y0 - 60)) < 1 and win.perch is not None)
# janela maximizada não derruba (navegador quase sempre está maximizado)
check("navegador maximizado: continua sentada no botão", win.perch is not None)
# outro botão igual bem longe (não é rolagem): não teleporta, cai
fake_items[:] = [item(y0 - 60 - 500)]
wait(lambda: win.perch is None, 2000)
check("item igual longe demais: não teleporta pra ele", win.perch is None and win.foot.y() > y0 - 500)
wait(lambda: win.fall_v is None, 4000)
fake_items[:] = [item(y0)]
wait(lambda: win.jump_to(fake_items[0], x), 2000)
wait(lambda: win.perch is not None and win.fall_v is None, 4000)
# trocou de aba: o mesmo botão na aba nova não vale
win.page.gen += 1
wait(lambda: win.perch is None, 2000)
check("trocou de aba: ela sai do botão (não fica num botão da outra página)", win.perch is None)
wait(lambda: win.fall_v is None, 4000)
fake_items[:] = [item(y0 - 60)]
wait(lambda: win.jump_to(fake_items[0], x), 2000)
wait(lambda: win.perch is not None and win.fall_v is None, 4000)
# o botão some (rolou pra fora, trocou de página) → cai
heard.clear()
fake_items[:] = []
wait(lambda: win.perch is None and win.fall_v is None and abs(win.foot.y() - ground) < 1, 4000)
check("botão sumiu: ela cai até o chão", win.perch is None and abs(win.foot.y() - ground) < 1)
check("botão sumiu: fala que caiu", "caiu" in heard)
check("parou de seguir a janela", win.page.track is None)
# outra janela tapa o botão → cai
fake_items[:] = [item(y0)]
wait(lambda: win.jump_to(fake_items[0], x), 2000)
wait(lambda: win.perch is not None and win.fall_v is None, 4000)
above[:] = [desktop.Win(999, "Outra", "x.exe", QRect(int(x - 300), int(y0 - 400), 600, 600), False, False)]
wait(lambda: win.perch is None and win.fall_v is None, 4000)
check("outra janela tapou o botão: ela cai", win.perch is None)
above[:] = []
# sozinha: sobe num item da página
fake_items[:] = [item(y0, "imagem:Foto:30", 400)]
wait(lambda: win.fall_v is None and abs(win.foot.y() - ground) < 1, 3000)
ok = False
for _ in range(6):  # 70% das vezes prefere item da página (sem janela de verdade aqui, sempre ele)
    if win.climb():
        ok = wait(lambda: win.perch is not None and win.fall_v is None, 8000)
        break
check("sozinha: sobe num item da página", ok and win.perch.el == "imagem:Foto:30")

# jogando ela com o mouse em cima do botão (o navegador não está mais na frente)
fake_items[:] = [item(y0, "botão:Curtir:15")]
win.jump_to(None, x)
wait(lambda: win.perch is None and win.fall_v is None and abs(win.foot.y() - ground) < 1, 4000)
win._start_drag()
win._drag_to(QPointF(x, y0 - 150))
win._end_drag()
wait(lambda: win.fall_v is None, 3000)
check("jogada no ar em cima do botão: cai e fica nele", win.perch is not None and win.perch.el == "botão:Curtir:15"
      and abs(win.foot.y() - y0) < 1)
win.jump_to(None, x)
wait(lambda: win.perch is None and win.fall_v is None and abs(win.foot.y() - ground) < 1, 4000)
win._start_drag()
win._drag_to(QPointF(x, y0 + 25))  # pés um pouco abaixo da borda (no meio do botão)
win._end_drag()
wait(lambda: win.fall_v is None, 3000)
check("solta com os pés no meio do botão: encaixa em cima", win.perch is not None and abs(win.foot.y() - y0) < 1)

win.page.close()
print("\n" + ("tudo certo" if not fails else f"{len(fails)} FALHA(S): {fails}"))
os._exit(1 if fails else 0)
