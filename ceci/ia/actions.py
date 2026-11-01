"""O que a Ceci sabe fazer com o corpo (animações e movimentos que já existem). O que você pede ("então dorme,
linda", "toma um café aí", "sobe na janela") é comparado com esta lista: pela IA, que marca [faz: nome] no fim
da resposta, e por palavras quando a IA esquece de marcar (ou caiu). Nada aqui mexe no computador.
"""
import re

from ..sala.texts import norm

# nome: (o que é, para a IA; animação ou movimento "_x" do App; jeitos de pedir, já sem acento)
ACTIONS = {
    "subir": ("pular pra cima de uma janela aberta e sentar lá", "_subir",
              r"\b(?:sobe|subir|suba|pula|pular|pule|senta|sentar|vai)\b.{0,20}\b(?:janela|aba|barra|navegador)\b"),
    "descer": ("pular da janela pro chão", "_descer",
               r"\b(?:desce|descer|desca|pula pro chao|sai da janela|volta pro chao)\b"),
    "dormir": ("tirar um cochilo / dormir", "cochilo",
               r"\b(?:dorme|dormir|durma|vai dormir|cochila|cochilar|tirar? um cochilo|vai nanar|nana|deita|descansa)\b"),
    "acordar": ("acordar", "_acordar", r"\b(?:acorda|acordar|acorde|levanta)\b"),
    "cafe": ("tomar café", "cafe",
             r"\b(?:toma|tomar|tome|bebe|beber|beba|pega|pegar|faz|fazer)\b.{0,15}\bcafe\b|\bcafezinho\b"),
    "ler_sentada": ("ler um livro sentada no chão", "lendo_chao",
                    r"\b(?:le|ler|leia|lendo)\b.{0,25}\b(?:sentada|no chao)\b"),
    "ler": ("ler um livro em pé (Percy Jackson)", "lendo",
            r"\b(?:le|ler|leia|vai ler|pega)\b.{0,15}\b(?:livro|percy jackson|algo|alguma coisa|um pouco)\b"
            r"|\bvai ler\b"),
    "gato": ("brincar com o Ozzy ou o Bowie", "gato",
             r"\b(?:brinca|brincar|brinque|chama|pega|faz carinho)\b.{0,20}\b(?:gatos?|gata|gatinhos?|ozzy|bowie)\b"),
    "acenar": ("acenar / dar oi ou tchau com a mão", "acenando",
               r"\b(?:acena|acenar|acene|da (?:um )?(?:tchau|oi)|manda (?:um )?(?:oi|tchau))\b"),
    "comemorar": ("comemorar / fazer festa / dançar", "sucesso",
                  r"\b(?:comemora|comemorar|faz festa|danca|dancar|dance|dancinha)\b"),
    "programar": ("programar no notebook", "programando",
                  r"\b(?:programar|vai programar|programa (?:um pouco|algo|ai)|coda|codar)\b"),
    "espreguicar": ("se espreguiçar", "espreguicando", r"\b(?:espreguica|espreguicar|se espreguica)\b"),
    "esconder": ("se esconder atrás da lateral da tela", "escondendo", r"\b(?:se esconde|esconde|esconder)\b"),
    "sentar": ("sentar na borda com as pernas balançando", "borda", r"\b(?:senta|sentar|sente|se senta)\b"),
    "passear": ("dar uma volta andando pela tela", "_passear",
                r"\b(?:passeia|passear|vai passear|da uma volta|anda um pouco|caminha)\b"),
}
TAG = re.compile(r"\[\s*faz\s*:\s*([^\]\n]{1,40}?)\s*\]", re.I)
# a resposta dela recusou ("não vou dormir porra"): o pedido não vira ação
REFUSED = re.compile(r"\b(?:nao|nem) (?:vou|quero|to a fim|rola|fodendo|a pau|ferrando|ferrou)\b|\bagora nao\b|"
                     r"\bdepois eu\b")
WORDS = 14  # pedido curto: "ontem eu dormi tarde e ..." não é pedido pra ela dormir

RULE = """
- AÇÕES DO SEU CORPO: na tela você consegue fazer de verdade só estas coisas: """ + "; ".join(
    f"{k} ({v[0]})" for k, v in ACTIONS.items()) + """. Quando o usuário pedir uma delas, com qualquer
  palavra ("então dorme, linda", "vai tirar um cochilo", "toma um café aí", "sobe na janela"), compare com essa
  lista e, se for fazer, termine a resposta com [faz: nome], com o nome exato da lista (uma por resposta). Pode
  usar também quando você mesma decidir fazer uma delas. Pedido que não bate com nada da lista: não marque nada
  e diga com a sua voz que isso você não faz; nunca finja que fez."""


def find(name):
    """Nome que a IA marcou → ação da lista (aceita o nome exato ou um jeito de pedir); None se não existe."""
    n = norm(name).strip().replace(" ", "_")
    if n in ACTIONS:
        return n
    return wanted(name.replace("_", " "), limit=None)


def wanted(text, limit=WORDS):
    """Pedido de ação na mensagem do usuário (comparando com os jeitos de pedir de cada ação); None se não tem."""
    t = norm(text or "")
    if limit and len(t.split()) > limit:
        return None
    for k, (_, _, pat) in ACTIONS.items():
        if re.search(pat, t):
            return k
    return None


def from_reply(raw, user_text, mood=None):
    """(texto sem [faz: ...], ação). A marca da IA vale; sem marca, o pedido do usuário vale se ela não recusou."""
    found = [find(m) for m in TAG.findall(raw or "")]
    text = TAG.sub("", raw or "").strip()
    act = next((a for a in found if a), None)
    if act is None and user_text and mood not in ("negando", "brava") and not REFUSED.search(norm(text)):
        act = wanted(user_text)
    return text, act
