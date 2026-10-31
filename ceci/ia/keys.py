"""Chaves das APIs de IA, guardadas com a proteção do Windows (DPAPI), fora da pasta do projeto.

Só o seu usuário do Windows, neste computador, abre o arquivo. Nenhuma chave vai para log, histórico,
settings.json ou para outro serviço: cada uma só segue no cabeçalho do próprio serviço.
"""
import json
import os
import re
import sys

from ..sala.protect import _dpapi
from ..settings import CONFIG_DIR

PATH = os.path.join(CONFIG_DIR, "chaves_ia.bin")
ENTROPY = b"CeciBot.ChavesIA.v1"
# o que parece chave em mensagens de erro dos serviços (alguns repetem parte dela) vira [chave]
SECRET = re.compile(r"\b(?:sk|gsk|AQ|AIza|ghp|github_pat|csk)[-_.A-Za-z0-9*]{6,}")
_memory = {}             # fora do Windows: só na memória, nunca em disco
_cache = (None, {})      # (mtime, tamanho) do arquivo → chaves


def load():
    global _cache
    if sys.platform != "win32":
        return dict(_memory)
    try:
        st = os.stat(PATH)
        stamp = (st.st_mtime_ns, st.st_size)
        if _cache[0] != stamp:
            with open(PATH, "rb") as f:
                _cache = (stamp, json.loads(_dpapi(f.read(), False, ENTROPY)))
        return dict(_cache[1])
    except (OSError, ValueError):
        return {}


def get(service):
    return load().get(service) or None


def put(service, value):
    """Salva (ou apaga, com valor vazio) a chave de um serviço."""
    data = load()
    if value and value.strip():
        data[service] = value.strip()
    else:
        data.pop(service, None)
    if sys.platform != "win32":
        _memory.clear()
        _memory.update(data)
        return
    os.makedirs(CONFIG_DIR, exist_ok=True)
    tmp = PATH + ".tmp"
    with open(tmp, "wb") as f:
        f.write(_dpapi(json.dumps(data).encode(), True, ENTROPY))
    os.replace(tmp, PATH)


def scrub(text):
    return SECRET.sub("[chave]", text or "")
