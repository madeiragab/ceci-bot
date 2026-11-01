"""Login na página oficial da Sala Virtual, numa janela do navegador padrão do Windows aberta pelo Playwright
(Brave, Chrome, Edge, Vivaldi, Opera...; Firefox e outros que não são Chromium caem no Edge).

Você digita CPF e senha direto no site do Moodle; a Ceci nunca vê nem guarda a senha. Quando o login
termina, ela copia só os cookies da sessão do domínio da Sala Virtual e fecha o navegador por completo
(o perfil temporário é apagado pelo próprio Playwright).
"""
import os
import re
import sys
import time
import urllib.parse


class LoginCancelled(Exception):
    pass


CHANNELS = ("msedge", "chrome", None)  # sem padrão Chromium: Edge (vem com o Windows), Chrome, Chromium do Playwright
CHROMIUM = ("brave.exe", "chrome.exe", "msedge.exe", "vivaldi.exe", "opera.exe", "opera_gx.exe", "chromium.exe",
            "thorium.exe", "yandex.exe", "arc.exe")


def default_browser():
    """Executável do navegador padrão do Windows (o que abre links https), ou None."""
    if sys.platform != "win32":
        return None
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\Shell\Associations\UrlAssociations\https\UserChoice") as k:
            prog = winreg.QueryValueEx(k, "ProgId")[0]
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, prog + r"\shell\open\command") as k:
            cmd = winreg.QueryValueEx(k, "")[0]
    except OSError:
        return None
    m = re.match(r'\s*"([^"]+)"|\s*(\S+)', cmd)
    exe = m and (m.group(1) or m.group(2))
    return exe if exe and os.path.isfile(exe) else None
LOGGED_IN_JS = ("() => !!(window.M && M.cfg && M.cfg.sesskey) && !!document.body"
                " && !document.body.classList.contains('notloggedin')")


def _launch(p, headless):
    last = None
    exe = default_browser()
    first = [("exe", exe)] if exe and os.path.basename(exe).lower() in CHROMIUM else []
    for how, ch in first + [("channel", c) for c in CHANNELS]:
        try:
            kw = {"headless": headless, "args": ["--window-size=560,780", "--no-first-run",
                                                  "--no-default-browser-check"]}
            if how == "exe":
                kw["executable_path"] = ch  # o navegador padrão, com perfil temporário (nada da sua sessão)
            elif ch:
                kw["channel"] = ch
            return p.chromium.launch(**kw)
        except Exception as e:  # não abriu: tenta o próximo
            last = e
    raise RuntimeError(f"não consegui abrir um navegador para o login ({last})")


def login(base, cancel=lambda: False, timeout=600, headless=False, on_page=None):
    """Abre o login oficial e espera você entrar. Devolve {cookies, ua}. Fecha o navegador sempre."""
    from playwright.sync_api import Error as PwError, sync_playwright

    base = base.rstrip("/")
    host = urllib.parse.urlsplit(base).hostname
    with sync_playwright() as p:
        browser = _launch(p, headless)
        try:
            ctx = browser.new_context(viewport=None, locale="pt-BR")
            page = ctx.new_page()
            page.goto(f"{base}/login/index.php", wait_until="domcontentloaded")
            page.bring_to_front()
            if on_page:
                on_page(page)  # só os testes usam (login falso no servidor de teste local)
            end = time.monotonic() + timeout
            while True:
                if cancel():
                    raise LoginCancelled("login cancelado")
                if page.is_closed() or not browser.is_connected():
                    raise LoginCancelled("a janela de login foi fechada antes de entrar")
                if time.monotonic() > end:
                    raise LoginCancelled(f"o login demorou demais ({timeout // 60} min); tente de novo")
                url = urllib.parse.urlsplit(page.url)
                if url.hostname == host and "/login/" not in url.path:
                    try:
                        if page.evaluate(LOGGED_IN_JS):
                            break
                    except PwError:
                        pass  # página trocando no meio da checagem
                try:
                    page.wait_for_timeout(400)
                except PwError:
                    raise LoginCancelled("a janela de login foi fechada antes de entrar")
            ua = page.evaluate("navigator.userAgent")
            cookies = [c for c in ctx.cookies(base) if host.endswith(c["domain"].lstrip("."))]
            return {"cookies": cookies, "ua": ua}
        finally:
            try:
                browser.close()
            except Exception:
                pass
