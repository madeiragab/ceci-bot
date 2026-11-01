"""Personalidade da Ceci igual em todos os seus PCs: a personalidade editada (ceci_personality.txt) e o humor e as
falas que a IA gerou pra ela (mente_ia.json) ficam numa pasta do OneDrive (SHARED_DIR, em settings.py), que o
próprio OneDrive sincroniza.

Fica só neste PC: a conversa (em PC novo ela começa do zero), chaves de IA e sessão da Sala Virtual (cifradas
pelo Windows, não abrem em outro PC), tamanho/posição e opções (settings.json) e logs. Sem OneDrive, tudo
continua em %APPDATA%.
"""
import os
import shutil

from .settings import CONFIG_DIR, SHARED_DIR

FILES = ("mente_ia.json", "ceci_personality.txt")


def migrate(local=CONFIG_DIR, shared=SHARED_DIR):
    """Na primeira vez em cada PC: leva a personalidade deste PC para a pasta compartilhada (vale a mais nova)."""
    if os.path.normcase(os.path.abspath(local)) == os.path.normcase(os.path.abspath(shared)):
        return
    try:
        os.makedirs(shared, exist_ok=True)
    except OSError:
        return
    for name in FILES:
        src, dst = os.path.join(local, name), os.path.join(shared, name)
        if not os.path.exists(src):
            continue
        try:
            if not os.path.exists(dst) or os.path.getmtime(src) > os.path.getmtime(dst):
                shutil.copy2(src, dst)
            os.replace(src, src + ".migrado")  # não migra de novo (e fica de backup)
        except OSError:
            pass
