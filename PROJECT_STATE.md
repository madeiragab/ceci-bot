# Ceci Bot — Estado do projeto (Fase 1)

## Implementado
- Análise das 55 spritesheets: `tools/NOTES_sheets.md`.
- `tools/extract.py`: chroma key com unmix de borda + despill + correção de sombras magenta,
  segmentação (vãos + picos das pernas), alinhamento pés/linha do chão (caminhada: pelo tronco).
  Correção manual por sheet: `cuts` (cortes) e `anchor` (deslocamento por quadro).
- Padronização entre folhas (cabeça, cor, posição):
  - `tools/facescale.py`: acha o rosto (óculos + olhos) em todos os quadros por template multi-escala
    (referência = idle 22.0; 2ª passada `--multi` com vários rostos já padronizados para as folhas
    antigas) e corrige o `mult` de escala de cada folha.
  - `tools/consistency.py`: correção de cor em Lab (`correct_colors`): pele, mechas vermelhas,
    pretos e roupa (tons médios marrom/cinza da calça/jaqueta).
  - `tools/palette.py`: paleta única — mede as 4 classes de cor em TODAS as folhas e ajusta cada uma
    rumo à mediana geral (iterativo; `--report` mostra o resíduo por folha).
  - `tools/register.py 57:0 22:0`: alinha uma folha pelo desenho inteiro (escala + x/y por silhueta
    e luminância). Usado no idle novo (57) contra a pose neutra 22.0 que as outras animações usam;
    folhas registradas ficam fora do `facescale --apply`.
  - `tools/facescale.py`: `BODY` mede pela altura do corpo as folhas de rosto virado (folha 3).
  - `tools/transitions.py`: confere TODAS as passagens do manifesto (entrada, passo a passo, volta
    do miolo, saída) pelo rosto e aponta saltos; `--apply` grava deslocamento x por folha.
  - `tools/overlay.py`: folha de conferência visual com o meio do dissolve de cada passagem entre folhas.
  - Ordem: `extract.py` → `facescale.py --apply` → `extract.py` → `facescale.py --multi --apply` →
    `extract.py` → `transitions.py --apply` → `extract.py` → `register.py 57:0 22:0` →
    `palette.py` → `extract.py` → `palette.py` → `sizematch.py` → `extract.py` → `facescale.py` →
    `stabilize.py` → `extract.py` → `facescale.py` → `transitions.py --apply` → `extract.py <folhas>` →
    `build_manifest.py`.
- `tools/build_manifest.py` → `assets/animations.json`: 56 animações com tempo por quadro feito à mão.
  Atividades têm início → miolo que repete (`loop` + `hold` em segundos) → final; o final só toca
  quando ela troca de animação (ex.: ler folheia 20–50 s e só guarda o livro ao trocar).
- Motor (`ceci/engine.py`): prioridade, miolo/hold/loops, pedido durante o miolo enfileira e toca o
  final antes, `cut` (arraste) imediato, `jump` (ir direto a um passo — pouso).
- App: janela transparente sem borda, dissolve entre quadros (exceto ciclo de pernas), respiração
  sutil quando parada (desligável; desligada no modo econômico), caminhada só para o lado com espaço
  e com velocidade casada à passada, arraste: encostar na borda de baixo → último quadro na hora;
  soltar no ar → "caindo" até o chão → impacto → levanta. Carinho, olhos seguem o mouse (6 direções),
  abre direto no idle novo (entrada pela porta opcional em Configurações), saída correndo, esconder na borda, cochilo/dormir (senta antes; acorda com os
  quadros do próprio sheet), menu, bandeja, configurações, painel de animações, pausa em tela cheia,
  início com o Windows, posição salva.

- Executável: `tools/build_exe.ps1` (PyInstaller 6.22, modo pasta, ícone `assets/icon/ceci.ico`) →
  `%LOCALAPPDATA%\Programs\Ceci Bot\Ceci Bot.exe` (138 MB, quase tudo Qt) + atalho "Ceci Bot" na área de
  trabalho. "Iniciar com o Windows" registra o próprio .exe.
- Configurações: .exe e código usam o MESMO arquivo, `%APPDATA%\Ceci Bot\settings.json` (antes o código
  usava `config/` do projeto, e abrir a versão de código parecia "esquecer" o tamanho escolhido no .exe).
  Tamanho mudado no diálogo ou no menu fica salvo até mudar de novo. Os testes usam uma pasta
  temporária (`CECI_CONFIG_DIR`) e nunca gravam nas configurações do usuário.
  Mudou sprite/manifesto/código → rodar o script de novo.

- Fechar: anda (caminhada) até o canto MAIS PERTO, corre e sai cortada pela borda da tela; espelhada
  no canto esquerdo. Folha 21 reduzida a 84 % (altura da corrida = altura do andar). Quadros 3–7 presos
  à borda: 4/6/7 têm o corte da tela no desenho; 3 e 5 (só o livro) ficam onde a mão o pega no quadro 6
  (−54/−50 px na arte original, convertidos pela escala da folha no build_manifest).

- Saída sem a perna aparecendo duas vezes: ordem agora corrida (0–2) → meio fora da tela (4) → só o
  livro (3, 5) → mão buscando (6, 7). Antes era 0–2 → livro → 4 → livro → mão, e ela "voltava" na borda.
  Quadro logo depois da corrida entra com corte seco (o dissolve mostrava dois corpos), e todo dissolve
  desenha o quadro anterior onde ele estava (pés presos à borda mudam de lugar entre quadros).
- Animações presas à parede (`edge` no manifesto; hoje o esconder) andam até a borda antes de começar,
  de qualquer origem (rotina, painel, menu). O ponto de partida (`edge_start`) é calculado para que,
  depois dos passos da própria animação, a agachada encoste na borda e o quadro preso continue dali.
  Antes, perto da borda ela pulava direto para o quadro 4 e era teleportada ao prender.
- Saída: folha 21 entrou na paleta única (cabelo estava mais vermelho; roupa fica sem ajuste porque
  metade dos quadros é só o livro/mão). Quadros com deslocamento (andar/correr) sem dissolve, para não
  deixar "fantasma" arrastando atrás dela.
- Publicado: https://github.com/madeiragab/ceci-bot (público), release v0.1.0 com `CeciBot-windows.zip`.
  Sem licença definida (todos os direitos reservados).

- Falas (`ceci/speech.py`, banco `assets/falas.json` v1.0: 242 frases em 29 categorias, texto do
  usuário sem alteração). Balão próprio (janela transparente aos cliques) em cima da cabeça, com
  rabicho; lá no alto (arrastada) vai para o lado da cabeça. Escreve letra a letra (38 ms por letra,
  pausa em pontuação), pisca ▼ no fim e some sozinho. Sentada/agachada o balão desce junto.
  - Interações sempre falam: clique, carinho, arraste, pouso, acordar, abrir, voltar a aparecer,
    menu "Interagir" e "Falar algo", painel de animações. Fechar: diz o tchau andando até o canto e só
    corre depois de terminar a frase; o balão some quando ela corre.
  - Cada animação tem sua categoria (`REACT`) e fala no começo do miolo (livro aberto, caneca na boca);
    automáticas só com chance × "Frequência das falas" e 18 s entre elas. Parada, solta um comentário a
    cada 45–110 s (8 % easter egg; "esperando" depois de 3 min sem interação; "Zzz" dormindo).
  - Nunca corta uma fala com outra: com o balão ocupado, interação entra numa fila (até 3, sem repetir
    categoria) e é dita em sequência, com pausa de leitura curta; fala automática é descartada.
  - Cada categoria é sorteada sem repetir até esgotar. Liga/desliga e frequência nas configurações.

## Testado de verdade
- `tests/speech_test.py` (24 checagens): escreve letra a letra, balão acima da cabeça e dentro da
  tela, rabicho na direção dela; clique e arraste no meio de uma frase entram na fila e saem na ordem
  (início → clique → arraste → pouso) sem cortar nenhuma; ao lado da cabeça quando arrastada lá no
  alto; sem repetição; intervalo das automáticas; desligar; some sozinho; tchau antes de correr.
- `tests/settings_test.py`: tamanho pelo diálogo e pelo menu continua ao abrir de novo.
- `tests/edge_test.py`: esconder do meio da tela e colada na borda anda antes, encosta (±4 px) e prende
  sem pulo para trás; saída na ordem 0,1,2,4,3,5,6,7. Prévias em `_preview/esconder_strip_*.png` e
  `_preview/saida_strip.png` conferidas.
- Falas na tela real (31/10): frase de início escrevendo, clique e carinho durante uma frase saem
  depois dela, arraste com o mouse real (pendurada → queda → "Meus óculos quase foram pro caralho!").
- Medição 31/10 com falas (bateria, 8 núcleos): .exe 60 s com rotina automática: CPU 0,47 % do total,
  working set 61 MB (máx. 65), privado 28 MB, 0 TCP. Isolando o balão (código, rotina parada): 0,35 %
  em silêncio × 0,45 % falando sem parar. Sem fala, o balão não tem timer nenhum.
- `tests/quit_test.py`: do meio da tela anda até o canto, sai pelo lado certo (espelhada à esquerda),
  quadros 4/6/7 colados na borda (±1,5 px) e o app só fecha no fim — dos dois lados.
- .exe aberto e medido por 30 s (31/10): rodando, CPU 0,20 % do total, 53 MB working set, 25 MB privado,
  0 conexões TCP. Atalho conferido (alvo e ícone apontam para o .exe).
- `tests/smoke_test.py`: todas as animações tocam sem erro e sem quadro faltando (offscreen).
- `tests/engine_test.py`: miolo repete; troca no miolo toca o final antes; arraste corta na hora.
- `tests/drag_test.py`: pouso ao encostar embaixo (último quadro), queda segura "caindo" e pousa no impacto.
- App rodando no desktop: transparência e posição sobre a barra de tarefas conferidas por screenshot.
- Medição em idle (30 s, primeira versão): CPU 0,07 %, RAM 60 MB (working set), 0 conexões de rede.
- Medição 31/10 (30 s após a entrada, com respiração + dissolve): CPU 1,6 % de um núcleo = 0,20 % do total
  (8 núcleos), working set 56 MB, privado 27 MB, 0 conexões TCP. A respiração é o principal custo;
  o modo econômico a desliga.
- Padronização das cabeças: rosto medido por template em todas as folhas ficou entre 0,93 e 1,07 do
  idle (antes: 0,98–1,44; a leitura, folha 19, estava ~30 % maior). Conferido visualmente em
  `_preview/trans_*.png` e `_preview/faces_cmp.png`. As folhas 2–20 casam com score menor (0,63–0,8)
  porque o rosto está virado (3/4) nos desenhos. Nelas a diferença que sobra (~±8 %) é estimativa.

- 31/10 (2ª rodada): idle novo `assetsoriginal/idle.png` (folha 57, respira e pisca) virou o idle
  principal; folha 56 (olhar para baixo) entrou no seguir_mouse (baixo-esq., baixo, baixo-dir.);
  seguir o mouse só começa com o cursor rápido (> 1800 px/s) e para após 2 s de mouse parado;
  folha 3 corrigida pela altura do corpo (estava 12 % maior; agora 333 px = idle); sentada
  balançando (51) com rosto travado nos quadros 2–7. Testes 4/4, 5/5, smoke ok. Medido: CPU 0,20 %
  do total, 57 MB working set, 28 MB privado, 0 TCP.

- Cores (paleta única, `tools/palette.py`): pele, mechas, pretos e roupa de TODAS as folhas rumo à
  mediana geral; diferença mediana entre folhas caiu de 4,6 para 2,1 Lab (pior ~5 Lab, na roupa).
  Idle novo (57) alinhado pela silhueta à pose neutra 22.0 (escala 0,99, dx +5, dy −6) e com a mesma
  paleta. Pés mais abertos no desenho do 57 ainda aparecem no dissolve; dissolve entre animações 420 ms.

- Tamanho igual ao idle novo (`tools/sizematch.py`): o 1º quadro em pé de cada folha (inclusive as
  antigas de cabeça grande, 2–20) nunca fica maior que o 57.0 na altura NEM na área (vale o menor fator).
  Ex.: fofa (4) estava +15 % de altura/+16 % de área → 0,99/1,00; apaixonada (20) +23 % → 1,01;
  sucesso/lembrete → área 1,00. Folhas sem pose em pé recebem o fator mediano.
- Ritmo: quase todas as animações a 1 quadro por segundo (mínimo 1000 ms por quadro). Fora da regra
  (`KEEP_PACE` em build_manifest.py): andar, arraste, porta, saída, esconder, olhar o mouse e o idle
  (piscada de 110–160 ms). Passos com deslocamento (`mv`) mantêm o tempo casado com a velocidade.

- Sem teleportes dentro das animações (`tools/stabilize.py`): cada quadro anda em x para a cabeça
  ficar parada (antes o alinhamento pelos pés fazia o corpo pular de lado ao agachar/sentar). Maior
  salto lateral dentro de uma animação caiu de ~98 px para ±10 px; feliz, curiosa, idle_fofo, leitura,
  ajeitando e soltar eram as piores. Início/fim de cada folha alinhados ao idle 57 (`transitions.py`).
- "Mover para outro canto" sempre anda (antes teletransportava quando longe ou com caminhada desligada).
- Olhar o mouse: cada direção fica no mínimo 1,5 s; depois de parar de olhar, 10 s até poder recomeçar.

## Não verificado ainda
- Seguir o mouse com gatilho de velocidade (limiar 1800 px/s) ainda não foi conferido com o mouse real.
- Arraste/clique/carinho com o mouse real (teste automatizado foi bloqueado; precisa do usuário).
- Clique atravessando áreas transparentes (comportamento padrão de janela layered do Qt no Windows).
- Saída animada pelo menu "Sair", multi-monitor e DPI > 100 %.

## Problemas conhecidos nos assets
- Não existe sheet de "investigando código com lupa", "esperando" ou "prestando atenção" dedicados.
- Não há piscar no traço novo (o piscar da sheet 2 foi removido junto com o idle antigo).
- Sheet 6 quadro 4 (porta sumindo) fica arroxeada; hologramas da sheet 10 ficam rosados.
- Mudanças de pose desenhadas em um passo só (ex.: em pé → sentada) continuam sendo um dissolve;
  não há quadros intermediários nos desenhos e eles não foram inventados.
