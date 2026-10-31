import json
import os
import sys

FROZEN = getattr(sys, "frozen", False)  # rodando como .exe (PyInstaller)
ROOT = getattr(sys, "_MEIPASS", "") if FROZEN else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# .exe e código usam o mesmo arquivo em %APPDATA%: tamanho e opções mudados valem até mudar de novo,
# seja qual for a versão aberta. Os testes apontam CECI_CONFIG_DIR para uma pasta temporária.
CONFIG_DIR = os.environ.get("CECI_CONFIG_DIR") or os.path.join(os.environ.get("APPDATA", ROOT), "Ceci Bot")
PATH = os.path.join(CONFIG_DIR, "settings.json")

DEFAULTS = {
    "size": 0.55,            # escala da personagem (1.0 = 340 px de altura)
    "speed": 1.0,            # multiplicador de velocidade das animações
    "fps": 30,               # limite p/ movimento e transições
    "random_freq": 1.0,      # frequência das animações aleatórias
    "walk": True,
    "follow_mouse": True,
    "petting": True,
    "specials": True,
    "always_on_top": True,
    "autostart": False,
    "pause_fullscreen": True,
    "eco": False,
    "breathe": True,
    "door_entrance": False,  # abrir já no idle novo; entrada pela porta é opcional
    "speech": True,          # falas no balão (letra a letra)
    "speech_freq": 1.0,      # frequência das falas automáticas
    "start_pos": "bottom_right",  # bottom_right | bottom_left | saved
    "pos": None,             # [x, y] do ponto dos pés (lógico)
    "ai_provider": "gemini_web",  # provedor da IA (ceci/ia/__init__.py: PROVIDERS)
    "ai_academic": None,     # pode mandar o recorte das atividades para a IA? None = ainda não perguntou
}


class Settings(dict):
    def __init__(self):
        super().__init__(DEFAULTS)
        try:
            with open(PATH, encoding="utf8") as f:
                self.update({k: v for k, v in json.load(f).items() if k in DEFAULTS})
        except (OSError, ValueError):
            pass

    def save(self):
        os.makedirs(CONFIG_DIR, exist_ok=True)
        tmp = PATH + ".tmp"
        with open(tmp, "w", encoding="utf8") as f:
            json.dump(dict(self), f, indent=1)
        os.replace(tmp, PATH)


def set_autostart(on):
    if sys.platform != "win32":
        return
    import winreg
    key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0,
                         winreg.KEY_SET_VALUE)
    try:
        if on:
            if FROZEN:
                cmd = f'"{sys.executable}"'
            else:
                exe = sys.executable.replace("python.exe", "pythonw.exe")
                cmd = f'"{exe}" "{os.path.join(ROOT, "main.py")}"'
            winreg.SetValueEx(key, "CeciBot", 0, winreg.REG_SZ, cmd)
        else:
            try:
                winreg.DeleteValue(key, "CeciBot")
            except FileNotFoundError:
                pass
    finally:
        winreg.CloseKey(key)
