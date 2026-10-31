# Pipeline dos sprites

As spritesheets originais (`assetsoriginal/`, fundo magenta, quadros na horizontal) viram os quadros
recortados de `assets/sprites/sNN/KK.png` e o índice `assets/frames.json`. O manifesto de animações
(`assets/animations.json`) é gerado à parte, por `tools/build_manifest.py`.

Dependências das ferramentas (não são necessárias para rodar o app):

```bash
pip install -r tools/requirements.txt   # Pillow, numpy, scipy
```

Rode sempre com `python -I` a partir da raiz do projeto.

## Etapas

| Ferramenta | O que faz | Grava |
|---|---|---|
| `extract.py [folhas]` | Chroma key com separação da borda, despill e sombras magenta viram preto translúcido. Segmenta os quadros pelos vãos e picos das pernas, sem supor 8 por folha, e alinha pelos pés e pela linha do chão. | `assets/sprites/`, `frames.json`, `_preview/aligned_NN.png` |
| `facescale.py [--multi] [--apply\|--apply-only]` | Acha o rosto (óculos e olhos) em cada quadro por template multiescala e corrige a escala de cada folha. `BODY` mede pela altura do corpo as folhas de rosto virado. | `assets/faces.json`, `mult` |
| `sizematch.py` | O 1º quadro em pé de cada folha nunca fica maior que o idle (57.0), nem na altura nem na área. | `mult` |
| `register.py 57:0 22:0` | Alinha uma folha pelo desenho inteiro (escala e x/y, pela silhueta e pela luminância). | `mult`, `dx`, `dy` |
| `palette.py [folhas] [--report]` | Paleta única de pele, mechas vermelhas, pretos e roupa, ajustada rumo à mediana de todas as folhas. É iterativa. | `*_src`, `d*` |
| `stabilize.py` | Mantém a cabeça parada dentro de cada animação, para o corpo não pular de lado ao agachar ou sentar. | `fdx` por quadro |
| `transitions.py [--apply]` | Confere todas as passagens do manifesto (entrada, passo a passo, miolo e saída) e alinha início e fim de cada folha ao idle. | `dx` |
| `overlay.py` | Gera folhas de conferência com o meio do dissolve de cada passagem entre folhas. | `_preview/trans_N.png` |
| `build_manifest.py` | Monta as 56 animações: tempo por quadro, miolo (`loop`), tempo de repetição (`hold`), prioridade, peso na rotina e deslocamento (`mv`/`pin`). | `animations.json` |

Todos os ajustes por folha ficam em `assets/consistency_targets.json`. Cada extração grava em
`frames.json` o que aplicou (`applied`), e as ferramentas seguintes partem disso.

## Ordem completa

```bash
python -I tools/extract.py
python -I tools/facescale.py --apply
python -I tools/extract.py
python -I tools/facescale.py --multi --apply
python -I tools/extract.py
python -I tools/register.py 57:0 22:0
python -I tools/palette.py
python -I tools/extract.py
python -I tools/palette.py
python -I tools/sizematch.py
python -I tools/extract.py
python -I tools/facescale.py
python -I tools/stabilize.py
python -I tools/extract.py
python -I tools/facescale.py
python -I tools/transitions.py --apply
python -I tools/extract.py <folhas indicadas>
python -I tools/build_manifest.py
```

## Ajustes manuais

Em `tools/extract.py`, dentro de `SHEETS`:

- `n`: número de quadros da folha.
- `cuts`: cortes manuais, em x do original.
- `anchor`: deslocamento `[dx, dy]` por quadro.
- `align: "torso"`: alinha pelo tronco em vez dos pés (andar, sentada balançando as pernas).
- `ref`: qual quadro é a pose em pé de referência.

Folhas com nome próprio, como `idle.png` = 57, ficam mapeadas em `FILES`. As anotações de cada folha
(conteúdo, continuações e quadros que seguram) estão em `tools/NOTES_sheets.md`.
