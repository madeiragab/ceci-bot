"""Sessão da Sala Virtual guardada com a proteção do Windows (DPAPI).

Só o seu usuário do Windows, neste computador, consegue abrir o arquivo. Nada de senha: guarda apenas os
cookies da sessão aberta pelo seu login na página oficial (e o link do calendário exportado, se houver).
"""
import ctypes
import json
import os
import sys
from ctypes import wintypes

from ..settings import CONFIG_DIR

PATH = os.path.join(CONFIG_DIR, "sala_virtual.sessao")
ENTROPY = b"CeciBot.SalaVirtual.v1"
_memory = None  # fora do Windows: só na memória, nunca em disco


class _Blob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _blob(data):
    buf = ctypes.create_string_buffer(data, len(data))
    return _Blob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char))), buf


def _dpapi(data, protect):
    c32 = ctypes.windll.crypt32
    src, _keep1 = _blob(data)
    ent, _keep2 = _blob(ENTROPY)
    out = _Blob()
    fn = c32.CryptProtectData if protect else c32.CryptUnprotectData
    if not fn(ctypes.byref(src), None, ctypes.byref(ent), None, None, 0x1, ctypes.byref(out)):  # UI_FORBIDDEN
        raise OSError("DPAPI recusou os dados")
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(out.pbData)


def save(data):
    global _memory
    raw = json.dumps(data).encode()
    if sys.platform != "win32":
        _memory = data
        return
    os.makedirs(CONFIG_DIR, exist_ok=True)
    tmp = PATH + ".tmp"
    with open(tmp, "wb") as f:
        f.write(_dpapi(raw, True))
    os.replace(tmp, PATH)


def load():
    if sys.platform != "win32":
        return _memory
    try:
        with open(PATH, "rb") as f:
            return json.loads(_dpapi(f.read(), False))
    except (OSError, ValueError):
        return None


def clear():
    global _memory
    _memory = None
    try:
        os.remove(PATH)
    except FileNotFoundError:
        pass
