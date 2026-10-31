"""Roteador central: cada mensagem da caixinha vira comando local, pergunta acadêmica ou conversa.

Comando local só com frase registrada (a mensagem inteira tem que bater com o padrão): uma frase parecida
não autoriza ação nenhuma; ela vai para a conversa. Nada aqui consulta a IA.
"""
import re
from collections import namedtuple

from ..sala.texts import norm

Route = namedtuple("Route", "kind action rest")  # kind: local | academico | conversa

_V = r"(?:me )?(?:mostra|mostrar|lista|listar|fala|ver)"
LOCAL = (
    ("atividades", rf"(?:{_V} )?(?:as |minhas |as minhas )?(?:atividades|tarefas|pendencias|pendentes)"),
    ("atrasadas", rf"(?:{_V} )?(?:as )?atrasadas"),
    ("hoje", r"hoje"),
    ("amanha", r"amanha"),
    ("semana", r"(?:a )?semana"),
    ("prazo", r"(?:proximo )?prazo|proxima(?: entrega)?"),
    ("resumo", rf"(?:(?:{_V}|me da) )?(?:o )?resumo(?: da faculdade)?"),
    ("conferir", r"(?:confere|conferir|atualiza|atualizar|sincroniza|sincronizar|checa)"
                 r"(?: a sala(?: virtual)?| as atividades)?"),
    ("conectar", r"(?:conecta|conectar)(?: a)?(?: sala(?: virtual)?)?"),
    ("configuracoes", r"(?:(?:abre|abrir|mostra)(?: as)? )?(?:configuracoes|config|ajustes)"),
    ("chat", r"(?:abre|abrir|mostra)(?: o)? (?:chat|historico)"),
    ("abrir_atividade", r"(?:abre|abrir)(?: a)? (?:atividade|tarefa|questionario)(?: de| do| da)? (?P<rest>.+)"),
    ("quieta", r"fica quiet(?:a|inha)|silencio|cala a boca|para de falar"),
    ("dormir", r"vai dormir|vai cochilar|dorme"),
    ("acordar", r"acorda"),
    ("passear", r"vai passear|passeia|da uma volta"),
    ("esconder", r"(?:se )?esconde"),
    ("falar", r"fala (?:algo|alguma coisa)"),
    ("cancelar", r"para|cancela|esquece(?: isso)?|deixa pra la"),
    ("de_novo", r"tenta de novo|de novo|tenta novamente"),
    ("nova_conversa", r"nova conversa|(?:esquece|apaga) (?:a|essa) conversa|reinicia a conversa"),
    ("dados_sim", r"pode (?:mandar|enviar) (?:meus )?(?:dados|prazos|atividades)(?: pra ia)?"),
    ("dados_nao", r"(?:nao|para de) (?:manda|mandar|envia|enviar) (?:meus )?(?:dados|prazos|atividades)(?: pra ia)?"),
    ("ajuda", r"ajuda|help|comandos"),
)
YES = {"sim", "pode", "pode sim", "claro", "manda", "ok", "beleza", "s"}
NO = {"nao", "nao pode", "melhor nao", "n"}

# palavras que pedem os dados da Sala Virtual (a pergunta vai com o recorte certo dos dados)
ACADEMIC = re.compile(r"\b(?:atividade|tarefa|questionario|forum|disciplina|materia|faculdade|sala virtual|"
                      r"atrasad\w*|pendent\w*|cronograma|relatorio|moodle)")
# genéricas: só contam quando a pergunta é sobre você ("tenho prova amanhã?"), não sobre outra pessoa
WEAK = re.compile(r"\b(?:trabalhos?|entregas?|entregar|prazos?|vence|vencendo|prova|provas|lista)\b")
MINE = re.compile(r"\b(?:tenho|tem algum\w*|meu|meus|minha|minhas|preciso|devo|eu|pra mim)\b")
OTHER = re.compile(r"\b(?:dela|dele|delas|deles)\b")
WHEN = re.compile(r"\b(?:hoje|amanha|semana|esse mes|este mes|fim de semana)\b")
FOLLOW = re.compile(r"^(?:e |mas |entao )|\b(?:delas|dessas|desses|deles|essa|esse|isso|primeiro|primeira|qual)\b")


def clean(text):
    t = norm(text).strip(" .!?,;")
    t = re.sub(r"^(?:ei |oi )?ceci[,!]?\s*", "", t)
    t = re.sub(r"\s*,?\s*por favor$|^por favor,?\s*", "", t)
    return t.strip(" .!?,;")


def route(text, last_topic=None, courses=(), consent_pending=False):
    t = clean(text)
    if consent_pending and t in YES | NO:
        return Route("local", "dados_sim" if t in YES else "dados_nao", "")
    for action, pat in LOCAL:
        m = re.fullmatch(pat, t)
        if m:
            return Route("local", action, (m.groupdict().get("rest") or "").strip())
    m = re.fullmatch(r"(?:nao fiz|desfaz\w*|desmarca\w*) (.+)", t)
    if m:
        return Route("local", "desfazer", m.group(1))
    m = re.fullmatch(r"(?:ja )?(?:fiz|feito|entreguei|terminei)(?: (.+))?", t)
    if m:
        return Route("local", "fiz", m.group(1) or "")
    if (ACADEMIC.search(t) or any(c and c in t for c in courses)
            or (WEAK.search(t) and (MINE.search(t) or WHEN.search(t)) and not OTHER.search(t))):
        return Route("academico", "", t)
    if last_topic == "academico" and len(t.split()) <= 9 and FOLLOW.search(t):
        return Route("academico", "seguimento", t)
    return Route("conversa", "", t)
