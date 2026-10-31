"""Fórmulas LaTeX da resposta ($...$, $$...$$, \\(...\\), \\[...\\]) → texto Unicode legível no balão e no chat.

Sem biblioteca: x^{4} → x⁴, x_1 → x₁, \\frac{a}{b} → a/b, \\sqrt{x} → √x, letras gregas e símbolos comuns.
O histórico guarda a resposta original; isto só muda o que aparece na tela.
"""
import re

SUP = dict(zip("0123456789+-=()nijkaebcdfghlmoprstuvwxyz",
               "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾ⁿⁱʲᵏᵃᵉᵇᶜᵈᶠᵍʰˡᵐᵒᵖʳˢᵗᵘᵛʷˣʸᶻ"))
SUB = dict(zip("0123456789+-=()aeoxijnmkhlpst", "₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎ₐₑₒₓᵢⱼₙₘₖₕₗₚₛₜ"))
SYMBOLS = {
    "alpha": "α", "beta": "β", "gamma": "γ", "delta": "δ", "epsilon": "ε", "varepsilon": "ε", "zeta": "ζ",
    "eta": "η", "theta": "θ", "lambda": "λ", "mu": "μ", "nu": "ν", "xi": "ξ", "pi": "π", "rho": "ρ",
    "sigma": "σ", "tau": "τ", "phi": "φ", "varphi": "φ", "chi": "χ", "psi": "ψ", "omega": "ω",
    "Gamma": "Γ", "Delta": "Δ", "Theta": "Θ", "Lambda": "Λ", "Pi": "Π", "Sigma": "Σ", "Phi": "Φ", "Omega": "Ω",
    "cdot": "·", "times": "×", "div": "÷", "pm": "±", "mp": "∓", "le": "≤", "leq": "≤", "ge": "≥", "geq": "≥",
    "neq": "≠", "ne": "≠", "approx": "≈", "equiv": "≡", "infty": "∞", "int": "∫", "iint": "∬", "oint": "∮",
    "sum": "∑", "prod": "∏", "partial": "∂", "nabla": "∇", "to": "→", "rightarrow": "→", "leftarrow": "←",
    "Rightarrow": "⇒", "Leftrightarrow": "⇔", "implies": "⇒", "iff": "⇔", "in": "∈", "notin": "∉",
    "subset": "⊂", "subseteq": "⊆", "cup": "∪", "cap": "∩", "emptyset": "∅", "forall": "∀", "exists": "∃",
    "neg": "¬", "land": "∧", "lor": "∨", "angle": "∠", "degree": "°", "circ": "°", "ldots": "…", "cdots": "⋯",
    "dots": "…", "quad": " ", "qquad": "  ", "lim": "lim", "log": "log", "ln": "ln", "sin": "sen", "cos": "cos",
    "tan": "tg", "max": "máx", "min": "mín", "mathbb{R}": "ℝ", "mathbb{N}": "ℕ", "mathbb{Z}": "ℤ",
    "mathbb{Q}": "ℚ", "mathbb{C}": "ℂ",
}
MATH = re.compile(r"\$\$(.+?)\$\$|\\\[(.+?)\\\]|\\\((.+?)\\\)|(?<![\\\w])\$(?!\s)([^$\n]+?)(?<!\s)\$(?!\d)", re.S)
GROUP = r"\{((?:[^{}]|\{[^{}]*\})*)\}"


def _script(s, table, mark):
    s = s.strip()
    if s and all(c in table for c in s):
        return "".join(table[c] for c in s)
    return f"{mark}({s})" if len(s) > 1 else mark + s


def _simple(s):
    return re.fullmatch(r"√?[\w.]+[⁰¹²³⁴⁵⁶⁷⁸⁹]*", s) is not None


def _frac(m):
    a, b = convert(m.group(1)), convert(m.group(2))
    return f"{a if _simple(a) else '(' + a + ')'}/{b if _simple(b) else '(' + b + ')'}"


def convert(expr):
    """Uma fórmula (sem os $) → texto."""
    t = expr.strip()
    for name in ("text", "mathrm", "mathbf", "mathit", "operatorname", "textbf", "boldsymbol"):
        t = re.sub(r"\\" + name + GROUP, r"\1", t)
    for _ in range(4):  # frações e raízes aninhadas
        t = re.sub(r"\\[dt]?frac\s*" + GROUP + r"\s*" + GROUP, _frac, t)
        t = re.sub(r"\\sqrt\s*\[([^\]]+)\]\s*" + GROUP,
                   lambda m: _script(m.group(1), SUP, "^") + "√" + _wrap(convert(m.group(2))), t)
        t = re.sub(r"\\sqrt\s*" + GROUP, lambda m: "√" + _wrap(convert(m.group(1))), t)
    t = re.sub(r"\\sqrt\s*(\w)", r"√\1", t)
    t = re.sub(r"\\(?:left|right|big|Big|bigg|Bigg)\s*([()\[\]|.]|\\[{}])", lambda m: m.group(1).strip(".\\"), t)
    for name in sorted(SYMBOLS, key=len, reverse=True):
        t = re.sub(r"\\" + re.escape(name) + r"(?![A-Za-z])", lambda m, s=SYMBOLS[name]: s, t)
    t = re.sub(r"\^\s*" + GROUP, lambda m: _script(convert(m.group(1)), SUP, "^"), t)
    t = re.sub(r"\^\s*(\\?\w)", lambda m: _script(m.group(1), SUP, "^"), t)
    t = re.sub(r"_\s*" + GROUP, lambda m: _script(convert(m.group(1)), SUB, "_"), t)
    t = re.sub(r"_\s*(\w)", lambda m: _script(m.group(1), SUB, "_"), t)
    t = re.sub(r"\\([,;:! ])", " ", t)
    t = re.sub(r"\\\\", " ", t)
    t = re.sub(r"\\([A-Za-z]+)", r"\1", t)  # comando desconhecido: fica o nome
    t = t.replace("{", "").replace("}", "")
    return re.sub(r"\s{2,}", " ", t).strip()


def _wrap(s):
    return s if _simple(s) else f"({s})"


def render(text):
    """Troca cada fórmula do texto pela versão legível; o resto fica igual."""
    return MATH.sub(lambda m: convert(next(g for g in m.groups() if g is not None)), text or "")
