"""Gera assets/animations.json (catálogo editável). Rode após tools/extract.py.

Cada animação tem início → miolo → final. O miolo (loop [i, j]) repete por "hold" [min_s, max_s]
segundos, "loops" vezes, ou "inf" (até o app pedir para sair). O final só toca quando ela vai trocar
de animação. Tempos em ms, escolhidos quadro a quadro.

Passo: [sheet, quadro, ms] ou [sheet, quadro, ms, {extras}]
extras: "rand": [min_ms, max_ms] (pausa variável), "mv": px/s (move a janela; + = direita),
"pin": "right" (borda do quadro na borda direita da tela), "dx": ajuste em px.
Passo com sheet 0 = quadro vazio.
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
A = {}


def anim(aid, name, cat, seq, loop=None, loops=None, hold=None, next="idle", prio=1, auto=0, mirror=False,
         **kw):
    A[aid] = dict(name=name, cat=cat, seq=seq, loop=loop, loops=loops, hold=hold, next=next, prio=prio,
                  auto=auto, mirror=mirror, **kw)


def S(sheet, *ms):
    """Passos de um sheet: S(30, 500, 800, ...) = quadro 0 por 500 ms, quadro 1 por 800 ms...
    None pula o quadro; negativo -n vira pausa variável entre n e 2n ms."""
    out = []
    for k, t in enumerate(ms):
        if t is None:
            continue
        out.append([sheet, k, -t, {"rand": [-t, -2 * t]}] if t < 0 else [sheet, k, t])
    return out


def F(sheet, frames, ms):
    return [[sheet, f, ms] for f in frames]


# ---------------- estados básicos ----------------
anim("idle", "Idle neutro (respira e pisca)", "básico", S(57, 2600, 2200, 2400, 110, 160, 1800, 2600, 2300),
     loop=[0, 7], loops="inf", prio=0, sheet=57)  # folha idle.png: 3-4 = piscada
anim("idle_fofo", "Idle fofo", "básico", S(2, 450, 900, 450, 500, 450, 900, 450, 700), auto=5, sheet=2)
anim("curiosa", "Curiosa / esperando", "básico", S(3, 500, 900, 500, 900, 500, 600, 1200, 600), auto=4, sheet=3)
anim("fofa", "Fofa (corações, gatinho)", "básico", S(4, 550, 1000, 550, 1200, 550, 550, 1200, 600), auto=3,
     sheet=4)
anim("ajeitando", "Ajeita óculos / bate o pé", "básico", S(7, 480, 480, 900, 480, 480, 900, 480, 550), auto=8,
     sheet=7)
anim("caminhar", "Caminhada", "básico", [[5, 0, 300]] + F(5, range(1, 9), 150) + [[5, 9, 300]],
     loop=[1, 8], loops="inf", mirror=True, sheet=5, walk=True, stride=300)
anim("entrada", "Entrada pela porta", "básico", S(6, 700, 650, 450, 550, 450, 900, 500), prio=5, sheet=6)
# saída: 0-2 corre (desloca a janela), 3-7 presos à borda da tela. 4/6/7 já têm o corte da tela na borda
# direita do desenho; 3 e 5 (só o livro) ficam onde a mão o pega no quadro 6: -54/-50 px na arte original
_s21 = json.load(open(os.path.join(ROOT, "assets", "frames.json"), encoding="utf8"))["21"]["scale"]
anim("saida", "Saída correndo da tela", "básico",
     # a perna aparece uma vez só: o quadro 4 (meio fora da tela) emenda direto na corrida, depois
     # só o livro (3, 5) e a mão voltando para buscá-lo (6, 7)
     [[21, 0, 220, {"mv": 300}], [21, 1, 220, {"mv": 300}], [21, 2, 240, {"mv": 300}],
      [21, 4, 550, {"pin": "right"}], [21, 3, 650, {"pin": "right", "dx": round(-54 * _s21)}],
      [21, 5, 700, {"pin": "right", "dx": round(-50 * _s21)}], [21, 6, 650, {"pin": "right"}],
      [21, 7, 550, {"pin": "right"}], [0, -1, 600]], next=None, prio=9, sheet=21, mirror=True)

# ---------------- pensamento e trabalho ----------------
anim("pensando", "Pensando", "trabalho", S(8, 500, 500, 500, 800, 800, 800, 600, 700), loop=[3, 5], hold=[4, 8],
     auto=2, sheet=8, special=True)
anim("processando", "Processando", "trabalho", S(9, 500, 700, 700, 700, 700, 700, 700, 600), loop=[1, 6],
     hold=[6, 12], sheet=9, special=True)
anim("trabalhando", "Trabalhando (hologramas)", "trabalho", S(10, 500, 500, 800, 800, 800, 800, 700),
     loop=[2, 5], hold=[8, 16], sheet=10, special=True)
anim("lembrete", "Mostrando lembrete", "trabalho", S(11, 500, 600, 1800, 600, 900), sheet=11, special=True)
anim("sucesso", "Sucesso", "trabalho", S(12, 500, 500, 1600, 600, 900), sheet=12, special=True)
anim("erro", "Erro", "trabalho", S(13, 600, 600, 800, 600, 700, 1600), sheet=13, special=True)

# ---------------- emoções ----------------
anim("feliz", "Feliz", "emoção", S(15, 350, 300, 300, 400, 350, 700), auto=2, sheet=15, special=True)
anim("brava", "Brava", "emoção", S(16, 600, 900, 600, 600, 600, 600, 1100), sheet=16, special=True)
anim("triste", "Triste", "emoção", S(17, 600, 600, 600, 800, 600, 700, 700, 800), loop=[2, 6], hold=[5, 10],
     sheet=17, special=True)
anim("apaixonada", "Apaixonadinha", "emoção", S(20, 600, 500, 900, 700, 700, 1300), sheet=20, special=True)
anim("confusa", "Confusa", "emoção", S(25, 500, 500, 500, 900, 900, 500, 500, 600), auto=2, sheet=25,
     special=True)
anim("assustada", "Assustada", "emoção", S(24, 350, 350, 600, 700, 500, 500, 500, 500), sheet=24, special=True)
anim("acenando", "Acenando", "emoção", S(22, 300, 300, 300, 300, 300, 300, 300, 450), loop=[2, 5], loops=2,
     prio=2, sheet=22)
anim("negando", "Negando", "emoção", S(23, 450, 450, 450, 600, 600, 450, 450, 500), sheet=23, special=True)
anim("beijinho", "Mandando beijinho", "emoção", S(26, 400, 400, 400, 400, 400, 1000, 400, 450), auto=1,
     sheet=26, special=True)
anim("coracao", "Coração com as mãos", "emoção", S(27, 400, 400, 400, 400, 1200, 400, 400, 450), auto=1,
     sheet=27, special=True)

# ---------------- comportamentos ----------------
anim("sonolenta", "Sonolenta", "comportamento", S(28, 500, 900, 700, 900, 900, 1000, 1000, 600), loop=[2, 6],
     hold=[4, 10], auto=3, sheet=28)
anim("cochilo", "Sentar e cochilar", "comportamento", S(29, 500, 900, 700, 800, 1400, 1400, 900, 700, 500),
     loop=[4, 5], hold=[30, 120], sheet=29)
anim("dormindo", "Dormindo (loop)", "comportamento", S(29, 500, 900, 700, 800, 1400, 1400, 900, 700, 500),
     loop=[4, 5], loops="inf", sheet=29)  # senta e cochila antes (nada de aparecer deitada do nada)
anim("acordando", "Acordando", "comportamento", S(53, 900, 700, 900, 800, 700, 600, 900, 600), sheet=53)
anim("espreguicando", "Espreguiçando", "comportamento", S(52, 500, 600, 600, 1000, 700, 900, 600, 500), auto=3,
     sheet=52)
anim("cafe", "Tomando café", "comportamento", S(30, 500, 800, -1500, 900, 1100, 900, 800, 500), loop=[2, 5],
     hold=[12, 30], auto=4, sheet=30)
anim("caneca", "Abraçando caneca", "comportamento",
     S(32, 500, 700, 900, 1000, 900, 900, 900, 700) + [[30, 6, 800], [30, 7, 500]],  # guarda na mochila (sheet 30)
     loop=[2, 6], hold=[8, 20], auto=3, sheet=32)
anim("lendo", "Lendo Percy Jackson (em pé)", "comportamento", S(19, 500, 700, 900, -2000, 700, 600, 700, 500),
     loop=[3, 4], hold=[20, 50], auto=3, sheet=19)
anim("lendo_chao", "Lendo Percy Jackson (sentada)", "comportamento",
     S(31, 500, 900, -2500, 1300, 800, -2000, 900, 600), loop=[2, 5], hold=[30, 90], auto=2, sheet=31)
anim("gato", "Interagindo com gato", "comportamento", S(18, 900, 700, 700, 800, -1500, 1200, 800, 1000),
     loop=[4, 5], hold=[10, 25], auto=2, sheet=18)
anim("borda", "Sentada na borda", "comportamento", S(51, 500, 600, 900, 700, 900, 700, 900, 900, 600),
     loop=[2, 7], hold=[10, 25], auto=2, sheet=51)
for _st in A["borda"]["seq"][2:8]:  # sentada na beirada da barra de tarefas (pernas por cima dela)
    _st.append({"sit": 1})

# ---------------- especiais (só visual nesta fase) ----------------
anim("tarefa", "Mostrando tarefa", "especial",
     S(33, 500, 800, 700, 900, 900, 900, 900, 700) + [[33, 1, 700], [33, 0, 400]],  # guarda a prancheta
     loop=[3, 6], hold=[4, 8], sheet=33, special=True)
anim("prazo", "Prazo urgente", "especial", S(34, 500, 600, 500, 500, 500, 500, 500, 500), loop=[4, 7], loops=2,
     sheet=34, special=True)
anim("sala_virtual", "Conferindo Sala Virtual", "especial", S(35, 500, 800, 900, 900, 900, 900, 800, 600),
     loop=[2, 5], hold=[8, 16], sheet=35, special=True)
anim("resumo", "Resumo do dia", "especial", S(36, 500, 800, 1000, 1000, 900, 1400, 800, 600), loop=[2, 5],
     hold=[8, 16], sheet=36, special=True)
anim("programando", "Programando (no chão)", "especial", S(37, 500, 800, 450, 450, 900, 700, 900, 600),
     loop=[2, 6], hold=[12, 30], sheet=37, special=True)
anim("programando_mesa", "Programando (na mesa)", "especial",
     S(14, 700, 700, 450, 450, 900, 450, 800) + [[14, 1, 600], [14, 0, 700]],  # levanta e sai da cadeira
     loop=[2, 6], hold=[15, 40], sheet=14, special=True)
anim("encontrando_bug", "Encontrando bug", "especial", S(38, 600, 600, 600, 600, 1100, 700, 700, 900), sheet=38,
     special=True)
anim("corrigindo_bug", "Corrigindo bug", "especial", S(39, 500, 600, 600, 600, 600, 600, 700, 900), loop=[1, 5],
     hold=[6, 12], sheet=39, special=True)
anim("testes", "Executando testes", "especial",
     S(40, 500, 800, 700, 500, 800, 700, 1600, 1400) + [[37, 7, 600]],  # levanta (sheet 37)
     loop=[3, 4], loops=[2, 3], sheet=40, special=True)
anim("aprovado", "Código aprovado", "especial", S(41, 500, 800, 600, 900, 1200, 1800) + [[37, 7, 600]],
     sheet=41, special=True)
anim("quebrou", "Código quebrou", "especial", S(42, 500, 800, 600, 1400, 900, 900, 1200, 600), sheet=42,
     special=True)
anim("observando", "Observando tela", "especial", S(43, 500, 500, 900, 500, 800, 500, 600), sheet=43,
     special=True)
anim("apontando", "Apontando erro", "especial", S(44, 500, 600, 900, 600, 700, 1500), sheet=44, special=True)
anim("explicando", "Explicando", "especial", S(45, 500, 1000, 1000, 1000, 1000, 1300), sheet=45, special=True)
anim("atualizando", "Atualizando dados", "especial", S(46, 500, 700, 600, 900, 900, 1400, 900), sheet=46,
     special=True)
anim("conversando", "Conversando (só visual)", "especial", S(50, 400, 450, 450, 450, 450, 450, 450, 500),
     loop=[1, 6], hold=[4, 8], sheet=50, special=True)
anim("chamando", "Chamando atenção", "especial", S(54, 350, 350, 350, 350, 350, 350, 350, 500), sheet=54,
     special=True)
anim("escondendo", "Escondendo-se na lateral", "especial",
     [[55, f, 220, {"mv": 150}] for f in range(4)] + S(55, None, None, None, None, 500, 500) +
     [[55, 6, 1500, {"pin": "right"}], [55, 7, 1200, {"pin": "right"}],
      [55, 6, 500, {"pin": "right"}], [55, 5, 500], [55, 4, 500]],
     loop=[6, 7], hold=[5, 12], sheet=55, special=True, edge="right")

# ---------------- interação ----------------
anim("seguir_mouse", "Seguindo mouse (C-55)", "interação", F(47, range(6), 500) + F(56, range(4), 500),
     prio=2, sheet=47, catalog="C-55",
     eyes={"left": [47, 0], "up": [47, 2], "right": [47, 3], "far_right": [47, 5],
           "down_left": [56, 0], "down": [56, 1], "down_right": [56, 3]})  # 56 = olhar p/ baixo (folha nova)
anim("carinho", "Recebendo carinho (C-56)", "interação", S(48, 450, 500, 600, 800, 1100, 1100, 600, 500),
     prio=3, sheet=48, catalog="C-56")
anim("arrastada", "Sendo arrastada (C-57)", "interação",
     [[49, 1, 180], [49, 2, 350], [49, 3, 350], [49, 4, 300], [49, 5, 500], [49, 6, 600], [49, 7, 400]],
     loop=[1, 2], loops="inf", prio=4, sheet=49, catalog="C-57",
     fall=3, land=4)  # passo "caindo" (segura até o chão) e passo do impacto ao tocar o chão

# ritmo: quase tudo a 1 quadro por segundo (pedido do usuário). Ficam fora as que dependem de
# deslocamento/reação: andar, arraste, porta, saída, esconder, olhar o mouse e o idle (piscada curta).
KEEP_PACE = ("caminhar", "arrastada", "entrada", "saida", "escondendo", "seguir_mouse", "idle")
for _aid, _a in A.items():
    if _aid in KEEP_PACE:
        continue
    for _st in _a["seq"]:
        if len(_st) > 3 and "mv" in _st[3]:
            continue  # passo que desloca a janela: tempo casado com a velocidade
        _st[2] = max(_st[2], 1000)

json.dump(A, open(os.path.join(ROOT, "assets", "animations.json"), "w", encoding="utf8"), ensure_ascii=False,
          indent=1)
print(len(A), "animações")
