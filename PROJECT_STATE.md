# Ceci Bot — Estado do projeto (Fases 1 e 2)

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
  - Girar ou sacudir no ar (`_spin_check`): em 1,5 s, mais de 500 px de caminho e 1,5 volta de curva
    (3 idas e vindas também contam) → fala "girando"; pode reclamar de novo a cada 6 s. Pousou depois
    de girar → "tonta" em vez de "solta". As duas categorias (20 frases) foram escritas por mim fora do
    banco v1.0 e estão marcadas no `_sobre` do falas.json; total agora 262 frases em 31 categorias.
- Tamanho "Mínima" (0,25, o menor que as configurações aceitam) no menu Alterar tamanho; conferido na
  tela com o balão legível (a fonte do balão não encolhe abaixo de 80 %).
- Clique nela (cabeça ou corpo) = "Interagir" (acenando, feliz, beijinho, coração ou fofa; mesma lista do
  menu, `INTERACT` em window.py) + fala de "clique". Clicar na cabeça não é mais carinho.
- Carinho só passando o mouse pela cabeça várias vezes: conta as mudanças de sentido do cursor (passada
  ≥ 25 px × escala, em x ou y); 5 idas e vindas em 3 s = carinho. Antes bastavam ~160 px de trajeto, e
  passar o mouse uma vez por cima já disparava.
- Sentada na borda (folha 51, `borda`): os quadros 2–7 descem 67 px (`SIT_DROP` em extract.py), o
  assento fica na linha do chão (topo da barra de tarefas) e as pernas balançam por cima da barra.
  Antes ela sentava no ar, com os pés no topo da barra. A janela cresceu (590 px de altura, 100 px abaixo
  dos pés) para as pernas não serem cortadas; nos quadros sentados (`sit` no manifesto) a janela se põe
  por cima de novo para a barra de tarefas não cobrir as pernas.
- "Animações deram uma bugada": observei o app rodando com log de cada quadro e não houve erro nem quadro
  fora do lugar. Vi duas Cecis abertas ao mesmo tempo (o .exe e uma de teste), uma por cima da outra, o
  que parece animação quebrada. Agora só abre uma (mutex nomeado `CeciBot.SingleInstance`); abrir de
  novo não faz nada. Se o problema voltar com uma Ceci só, ainda falta descobrir a causa.

- Clique x carinho x arraste (31/10): o carinho somava as voltas do mouse nos dois eixos, então o caminho
  torto da mira até a cabeça já virava carinho (simulado: 5 reversões com o algoritmo antigo). Agora conta
  por eixo (5 idas e vindas ≥ 30 px no mesmo eixo) e espera 450 ms: clicou nesse meio-tempo, vale o clique.
  Arraste só começa com um puxão (> 22 px) ou segurando 0,25 s e mexendo > 6 px; antes 6 px bastavam e um
  clique tremido (ou toque no touchpad) levantava a Ceci.

## Fase 2 — Sala Virtual (31/10)

### Inspeção (feita de verdade, sem login)
- `tool_mobile_get_public_config` (público) da Sala Virtual 2: Moodle 4.x (tema academi), `enablewebservices: 0`
  e `enablemobilewebservice: 0` → não existe API/token para aluno. Login por CPF + senha no formulário padrão,
  sem SSO. `M.cfg.sessiontimeout = 28800` → a sessão do Moodle expira com 8 h sem uso.
- Por isso: login na página oficial numa janela do Edge (Playwright, canal `msedge`, sem baixar navegador) e,
  depois, leitura pelas mesmas chamadas AJAX que o Painel usa (`lib/ajax/service.php`, com a sessão do
  usuário) + as páginas das atividades, via `urllib`. Nenhum navegador durante as consultas.

### Implementado (`ceci/sala/`)
- `login.py`: abre `/login/index.php`, espera o Painel logado (M.cfg.sesskey e sem `notloggedin`), copia só os
  cookies do domínio e fecha o navegador sempre (finally). Fechar a janela/cancelar/10 min = erro claro.
- `protect.py`: sessão (cookies, user agent, link do calendário exportado) cifrada com DPAPI
  (CryptProtectData, só o usuário do Windows neste PC). Nunca guarda senha.
- `moodle.py`: cliente HTTP com cookie jar; detecta sessão expirada (redirecionou para o login ou
  `servicerequireslogin`/`invalidsesskey`), sem internet (DNS), servidor fora (5xx/timeout/recusa).
  Leitores: M.cfg, datas do cabeçalho `activity-dates` e da tabela de status (português e inglês),
  status de envio (`submissionstatus*` ou texto), tentativas do questionário, página de erro (`errorbox`/404),
  calendário exportado (iCal) e o formulário "Obter URL do calendário".
- `collect.py`: disciplinas (`allincludinghidden`, as passadas só registradas), Linha do tempo (60 dias para
  trás, paginada), calendário mensal (mês passado + 6 à frente, eventos de módulo e de disciplina/usuário),
  conteúdo de cada disciplina (`core_courseformat_get_state`, plano B: links da página da disciplina) e
  página de cada tarefa/questionário (status de envio). Chave estável `cm:<id do módulo>` (eventos sem módulo:
  `ev:<id>`). Sumiu? Abre a página antes de marcar indisponível. Recursos (arquivo, link, página) ficam de fora;
  fórum/outros só com prazo ou conclusão acompanhada.
- `store.py` (SQLite `%APPDATA%\Ceci Bot\sala_virtual.db`): courses, activities, events (id do evento → atividade),
  changes (histórico), syncs, notifications (UNIQUE chave+tipo+prazo), prefs. Mudanças: nova (não na primeira
  sincronização), prazo (antes/depois, inclusive prazo definido/removido), entregue, reaberta, indisponível,
  voltou, atrasada. Nada é apagado. Na dúvida, mantém o prazo conhecido (só tira um prazo se o calendário
  foi lido por inteiro naquele período e a página também não mostra). Atividade que veio só do calendário
  é "adotada" pelo id do módulo depois, sem virar "nova" de novo.
- Status: pendente, entrega confirmada pelo Moodle, concluída (critério do Moodle; para tarefa/questionário
  só vale o envio), atrasada, sem prazo, desconhecido, marcada por você (não conta como entrega), indisponível,
  evento. Rascunho nunca é entrega.
- `reminders.py`: 7 d, 3 d, 24 h, 2 h, no dia (no horário da consulta) e atraso (só nos 3 primeiros dias).
  Só o aviso mais recente que já chegou é dado; os que ficaram para trás são marcados como pulados.
- `service.py`: uma tentativa automática por dia (registrada ao começar, falhou = não repete), consulta
  pendente ao abrir o app (20 s depois de ela entrar), manual não gasta a automática, um único timer local
  até o próximo lembrete/horário (máx. 3 h, sem rede). Sessão expirada + calendário exportado: confere só os
  prazos e marca como parcial. Horário silencioso e tela cheia seguram os avisos (importantes: configurável).
  Log sem sesskey/cookie/token.
- `ui.py`/`texts.py`: Conectar Sala Virtual (endereço, entrar, conferir, desconectar e apagar, horário,
  lembretes, silêncio), Minhas atividades, Resumo da faculdade, cartão de aviso com "Abrir no Moodle".
  Tema preto/vermelho. Falas novas `sv_*` com o texto do usuário (separadas pelo resultado real).
- App: animações Conferindo Sala Virtual → Atualizando dados → Sucesso/Erro/Confusa; Mostrando tarefa (nova),
  Mostrando lembrete (7/3 dias), Prazo urgente (24 h/dia/2 h/atraso), Resumo do dia (vários avisos ou primeira
  sincronização), Feliz (entrega confirmada). Pausada, oculta ou em tela cheia: não anima nem fala.
- .exe: `--collect-all playwright --collect-data tzdata`; pasta foi para ~248 MB (o driver do Playwright tem 107 MB).

### Testado de verdade (Fase 2)
- `tests/sala_test.py` (50 checagens) contra um Moodle falso local (`tests/fake_moodle.py`, dados fictícios):
  os 18 cenários obrigatórios (primeira sincronização, nova, prazo alterado, vencida, entregue, rascunho, sem
  data, removida, disciplina vazia, sem internet e servidor fora, sessão expirada (com e sem calendário
  exportado), parcial, duplicatas, aviso repetido, 1 automática por dia + consulta pendente ao abrir, manual,
  lembretes offline sem tocar no servidor, navegador encerrado depois do login com Edge de verdade em modo
  headless) + DPAPI, horário silencioso, logs sem segredos e janelas abrindo.
- `tests/sala_app_test.py` (9): ordem das animações, falas só do resultado real, cartão, pausada não reage.
- Visual das janelas conferido (render real, fora da tela) em `_preview/fase2_*.png`.
- Medido: .exe parado 0,09 % de CPU, 68 MB working set, 33 MB privado, 0 filhos, 0 TCP. Consulta (Moodle falso,
  46 atividades): 59 requisições, 0,7 s, 0,38 s de CPU, +2,6 MB, 0 processos filhos. Login: pico de 9 processos
  (Edge + driver) e ~500 MB por ~3 s; 0 processos depois.

### Verificado com a conta real (31/10, login feito pelo usuário)
- Login pelo .exe (Edge pela janela do Playwright empacotado), sessão salva e calendário exportado disponível.
- Consultas reais: 35 disciplinas e 144 atividades, resultado "ok", 126–180 s (pausa de 0,15 s entre requisições).
- Prazos conferidos com o texto do título das atividades ("Prazo: 07/10" → 07/10 23:59; "até 03/11 às 23:59").
- Tarefa: o status de envio bate com a página ("Enviado para avaliação" → entregue; "Nenhum envio foi feito ainda"
  → não enviada).
- Questionário: o leitor procurava a tabela antiga `quizattemptsummary`, mas a Sala Virtual (Moodle 4.5) mostra
  um cartão por tentativa com `quizreviewsummary` ("Situação: Finalizada") e o botão em `quizstartbuttondiv`.
  Resultado: 0 de 22 questionários aparecia como feito. Corrigido; na consulta seguinte, 9 foram reconhecidos como
  entregues. O Moodle de teste agora imita esse HTML. Seis questionários fechados não mostram tentativa nem botão:
  ficam como "desconhecido".

### Ela fala, sem janela (31/10, pedido do usuário)
- Avisos: falados no balão, um atrás do outro (`Speech.say_many`, sem o limite de 3 da fila das interações).
  Sem cartão. Notificação do Windows só quando ela não pode falar (pausada, oculta, tela cheia).
- Removidos: janelas Minhas atividades e Resumo da faculdade e o cartão de aviso. O menu agora faz ela falar.
- Clique duplo: caixinha (`ceci/command.py`) com palavras-chave fixas (atividades, prazo, hoje, amanhã, semana,
  atrasadas, resumo, conferir, fiz/não fiz + nome, ajuda...). O que não entende, diz que não entendeu. O clique
  simples espera o intervalo do clique duplo do Windows antes de Interagir, para o duplo não fazer as duas coisas.
  A caixinha é uma barrinha sem moldura e quase transparente; a resposta corta o que ela estava falando e a fila.
- Falas românticas tiradas: a categoria `apaixonada` inteira (beijinho/coração/fofa ficam sem fala, só a animação),
  "Beijinho!", "❤️", "Sentiu saudade?", "Tá carente hoje?", "Awnnn... seu idiota.". Agora 274 frases em 41 categorias.
- Testado: sala_test 53, sala_app_test 13 (caixinha responde na hora e diz quando não entende), interact_test 16 (clique
  duplo não faz Interagir), speech_test 24. A caixinha não foi testada na tela de verdade, só no modo sem tela.

### Não verificado ainda (Fase 2)
- Clique na notificação do Windows; consulta automática das 08:00 com a sessão já expirada (fallback pelo calendário).

## Testado de verdade
- `tests/speech_test.py` (24 checagens): escreve letra a letra, balão acima da cabeça e dentro da
  tela, rabicho na direção dela; clique e arraste no meio de uma frase entram na fila e saem na ordem
  (início → clique → arraste → pouso) sem cortar nenhuma; ao lado da cabeça quando arrastada lá no
  alto; sem repetição; intervalo das automáticas; desligar; some sozinho; tchau antes de correr.
- `tests/settings_test.py`: tamanho pelo diálogo e pelo menu continua ao abrir de novo.
- `tests/spin_test.py`: arrastar reto não conta; girar fala "girando" (depois do arraste, na fila) e
  pousa "tonta"; sacudir de um lado para o outro também conta.
- `tests/interact_test.py` (11 checagens): clique no corpo e na cabeça = Interagir com fala de clique;
  uma passada só não é carinho, vai e volta 5 vezes é; sentada na borda as pernas descem abaixo do
  chão, cabem na janela e o assento fica no chão (±12 px); a segunda Ceci não abre.
- Sentada na barra na tela real (31/10, tamanho Média): assento no topo da barra de tarefas, pernas por
  cima da barra na frente do relógio. Prévia offscreen em `_preview/sentada_barra.png`.
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
