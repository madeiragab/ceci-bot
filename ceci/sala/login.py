"""Login na página oficial da Sala Virtual, numa janela do Edge aberta pelo Playwright.

Você digita CPF e senha direto no site do Moodle; a Ceci nunca vê nem guarda a senha. Quando o login
termina, ela copia só os cookies da sessão do domínio da Sala Virtual e fecha o navegador por completo
(o perfil temporário é apagado pelo próprio Playwright).
"""
import time
import urllib.parse


class LoginCancelled(Exception):
    pass


CHANNELS = ("msedge", "chrome", None)  # Edge vem com o Windows; None = Chromium do Playwright, se instalado
LOGGED_IN_JS = ("() => !!(window.M && M.cfg && M.cfg.sesskey) && !!document.body"
                " && !document.body.classList.contains('notloggedin')")


def _launch(p, headless):
    last = None
    for ch in CHANNELS:
        try:
            kw = {"headless": headless, "args": ["--window-size=560,780", "--no-first-run",
                                                  "--no-default-browser-check"]}
            if ch:
                kw["channel"] = ch
            return p.chromium.launch(**kw)
        except Exception as e:  # canal não instalado: tenta o próximo
            last = e
    raise RuntimeError(f"não encontrei o Microsoft Edge nem o Chrome para abrir o login ({last})")


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
