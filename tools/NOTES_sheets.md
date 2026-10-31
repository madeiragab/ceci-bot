# Notas de análise visual (N = quadros reais)
1: N8 idle neutro -> olha p/ cima/lados (olhar curioso)
2: N8 idle piscando/piscadinha (fofo). fundo com gradiente rosa claro embaixo
3: N8 curiosa '?' (pares), ultimo par agachada -> confusa/curiosa
4: N8 fofa: coração, ajoelhada, piscadinha, gato, segurando algo
5: N10 caminhada: 0 frente, 1-8 ciclo lateral (direita), 9 frente
6: N7 entrada porta: 0-1 porta, 2-3 acena, 4(sliver)+5 porta sumindo, 6 surpresa !!, 7 idle
7: N8 idle variado: ajusta óculos, bate pé, coração
8: N8 pensando: !, ..., engrenagens, ?, brilho
9: N8 pensando c/ mão no queixo (?, ..., engrenagem) -> processando/pensando2
10: N7 laptop + hologramas (pastas, mapa) -> trabalhando/atualizando dados
11: N5 laptop -> sino lembrete (mostrando lembrete), termina coração
12: N5 laptop -> check verde (sucesso)
13: N6 laptop -> ?, espiral, !, suor, agachada, janela X (erro)
14: N7 anda até cadeira (0), senta na mesa (1), digita 2-6 (programando; loop 2-6)
15: N6 feliz pulando (sombra no chão faz parte)
16: N7 brava (fundo mais escuro/gradiente)
17: N8 triste chorando (mãos no rosto)
18: N8 gato: gato chega, agacha, pega no colo, abraça, solta, gato vai embora (gato varia posição -> modo cell)
19: N8 Percy Jackson: tira livro da mochila, lê (3-5), guarda (6), idle (7). segurar quadros de leitura
20: N6 apaixonadinha (5 = carta com coração)
21: N8? saída: 0-2 corre p/ direita (livro cai), 3 livro no chão, 4 meio fora da tela, 5 só livro, 6 mão pega, 7 mão+livro sumindo, último vazio -> modo cell (NÃO recentralizar)
22: N8 acenando
23: N8 braços cruzados balançando cabeça -> negando
24: N8 assustada (pulo com sombra)
REGRA: transições suaves, sem teleporte. Porta (6) e saída (21) e gato (18) usam posição na célula.
25: N8 confusa (?, rabisco)
26: N8 mandando beijinho
27: N8 coração com as mãos
28: N8 sonolenta (boceja, olhos caindo, zz, desperta)
29: N8 senta->cochila(4-5 loop zz)->acorda(6)->levanta(7). base p/ dormindo/acordando
30: N8 café: tira caneca da mochila(1), bebe 2-5, guarda(6), idle(7)
31: N8 senta no chão e lê PJ: 1 senta, 2-5 lê (segurar), 6 fecha, 7 em pé c/ livro
32: N8 abraçando caneca
GRID: maioria uniforme -> largura/N. Sheets 2172=8 células; 1916=8; 1672/1654=8; #5=10; #16=7; #20=6.
33: N8 mostrando tarefa: tira prancheta da mochila(1-2), mostra 3-6, guarda 7
34: N8 prazo urgente: olha relógio, raios, placa '!' (4-7)
35: N8 Sala Virtual (anim): senta c/ laptop(1), olha 2-5, fecha(6), em pé(7)
36: N8 resumo do dia: senta c/ caderno, gráfico, fecha, em pé
37: N8 programando sentado no chão (TAC TAC, janelas), levanta(7)
38: N8 em pé c/ laptop: digita, foca, bug!(4), feliz, joinha, coração -> encontrando bug
39: N8 em pé c/ laptop: digitando concentrada, sorri -> corrigindo bug
40: N8 executando testes: senta, bug, digita, ..., barra progresso, concluído
41: N8 código aprovado: senta, digita, testes, termina SENTADA c/ 'Código aprovado' -> precisa transição p/ levantar (usar 42[7]/37[7] em pé c/ laptop)
42: N8 código quebrou: senta, digita, erro compilação, rabisco, chora, desaba(6), levanta(7)
43: N7 observando/curiosa: !, ?, dedinho, brilho, neutra, em pé c/ tablet (último)
44: N6+brilho apontando erro: coça cabeça, ?, pensa, !, aponta p/ direita (brilho separado pertence ao último). NÃO é grid uniforme
45: N6 explicando (quadro branco, diagrama, lâmpada)
46: N7 atualizando dados (tablet sincronizando -> concluída)
47: N6 seguindo mouse (C-55): olhos em direções diferentes (analisar pupilas)
48: N8 recebendo carinho (C-56): fecha olhos, sorri, corações
49: N8 arrastada (C-57): 0 idle,1 susto,2-3 suspensa (loop no arraste),4 caindo,5 pouso agachada,6 recupera,7 idle
50: N8 conversando (gestos)
51: N8 sentada na borda: vira(1), senta pernas balançando 2-6 (loop), levanta(7)
52: N8 espreguiçando
53: N8 acordando: começa encolhida dormindo(0), acorda, esfrega olhos, levanta, espreguiça, em pé
54: N8 chamando atenção (acena com as duas mãos)
55: N8 escondendo na lateral: anda p/ direita, agacha, se esconde cortada na borda direita (6-7) -> precisa estar na borda da tela
NÃO ENCONTRADO: lupa/investigando código, esperando, prestando atenção dedicadas. Dormindo = 29[4-5]
ALINHAMENTO: y = linha de chão do sheet (preserva pulo/suspensão); x = centro dos pés (banda inferior do maior componente)

56: N4 (folha nova) olhando para baixo: esq.-baixo, baixo, dir.-baixo, dir.-baixo -> seguir_mouse (baixo)
57 (idle.png): N8 (folha nova) idle de frente que respira e pisca (3-4 olho fechado) -> idle principal
