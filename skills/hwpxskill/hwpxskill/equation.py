"""한글 수식(hp:equation) — 스크립트 검사, 크기 추정, 삽입용 XML, 목록·교체.

입력 문법은 한글 수식 편집기 스크립트만 받는다 (예: `{a+b} over {2}`, `sqrt {x}`,
`sum from {k=1} to {n} k`). LaTeX는 변환하지 않고, 섞여 들어오면 검사기가 오류로 알린다.

크기 추정은 한컴 저장본 60개 수식의 실제 크기(hp:sz)로 맞춘 근사치다. 한글은 수식을
열 때 다시 그리므로 몇 % 오차는 줄 배치에만 영향을 준다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from .core import xmlspan

# ── 한글 수식 명령어 ──────────────────────────────────────────────────
GREEK = ["alpha", "beta", "gamma", "delta", "epsilon", "zeta", "eta", "theta", "iota", "kappa", "lambda",
         "mu", "nu", "xi", "omicron", "pi", "rho", "sigma", "tau", "upsilon", "phi", "chi", "psi", "omega"]
GREEK_ALL = set(GREEK) | {g.upper() for g in GREEK} | {"vartheta", "varphi", "varpi", "varsigma", "varepsilon"}
SYMBOL_WORDS = {
    "TIMES", "times", "DIV", "div", "cdot", "CDOT", "LEQ", "leq", "GEQ", "geq", "NEQ", "neq", "SIM", "APPROX",
    "SIMEQ", "CONG", "EQUIV", "PROPTO", "IN", "NOTIN", "OWNS", "SUBSET", "SUPERSET", "SUBSETEQ", "SUPSETEQ",
    "CUP", "SMALLINTER", "UNION", "INTER", "OPLUS", "OMINUS", "OTIMES", "ODIV", "ODOT", "LOR", "LAND",
    "PREC", "SUCC", "UPLUS", "CIRC", "BULLET", "DEG", "AST", "STAR", "BIGCIRC", "EMPTYSET", "THEREFORE",
    "BECAUSE", "EXIST", "FORALL", "DIAMOND", "prime", "Partial", "partial", "INF", "inf", "infty", "NABLA",
    "larrow", "rarrow", "uparrow", "downarrow", "LARROW", "RARROW", "UPARROW", "DOWNARROW", "udarrow",
    "UDARROW", "LRARROW", "lrarrow", "NWARROW", "SEARROW", "NEARROW", "SWARROW", "HOOKLEFT", "HOOKRIGHT",
    "PVER", "MAPSTO", "CDOTS", "LDOTS", "VDOTS", "DDOTS", "cdots", "ldots", "vdots", "ddots", "DAGGER",
    "DDAGGER", "DOTEQ", "image", "REIMAGE", "ASYMP", "ISO", "DSUM", "XOR", "TRIANGLE", "NABLA", "ANGLE",
    "MSANGLE", "SANGLE", "VDASH", "DASHV", "BOT", "TOP", "MODELS", "LAPLACE", "CENTIGRADE", "FAHRENHEIT",
    "LSLANT", "RSLANT", "ATT", "HUND", "THOU", "IDENTICAL", "RTANGLE", "BASE", "BENZENE", "SQCAP", "SQCUP",
    "SQSUBSET", "SQSUBSETEQ", "PERP", "perp", "LNOT", "lnot", "ALEPH", "HBAR", "IMATH", "JMATH", "LITER",
    "WP", "Re", "Im", "DEG", "ohm", "mho", "ANGSTROM", "therefore", "because", "circ", "bullet", "star",
    "emptyset", "forall", "exist", "sim", "approx", "cong", "equiv", "subset", "supset", "in", "notin",
}
BIG_OPS = {"sum", "SUM", "prod", "PROD", "coprod", "SMALLSUM", "SMALLPROD", "SMCOPROD", "int", "INT", "dint",
           "tint", "oint", "odint", "otint", "inter", "union", "BIGSQCUP", "BIGSQCAP", "BIGOPLUS", "BIGOTIMES",
           "BIGODOT", "BIGUPLUS", "BIGOMINUS", "BIGODIV", "lim", "Lim", "LIM"}
FUNCS = {"sin", "cos", "tan", "cot", "sec", "csc", "sinh", "cosh", "tanh", "coth", "arcsin", "arccos",
         "arctan", "log", "ln", "lg", "exp", "det", "max", "min", "sup", "inf", "gcd", "lcm", "mod", "deg",
         "dim", "ker", "hom", "arg", "Pr", "lim"}
DECOR = {"bar", "vec", "hat", "tilde", "dot", "ddot", "under", "acute", "grave", "check", "arch", "dyad",
         "overline", "underline", "BOX", "OVERBRACE", "UNDERBRACE", "not", "box"}
MATRIX = {"matrix", "pmatrix", "bmatrix", "dmatrix", "cases", "eqalign", "pile", "lpile", "rpile", "CASES"}
FONT_WORDS = {"rm", "it", "bold", "RM", "IT", "BOLD"}
STRUCT_WORDS = {"over", "atop", "sqrt", "root", "of", "from", "to", "left", "right", "LEFT", "RIGHT",
                "sup", "sub", "lsup", "lsub", "SQRT", "OVER", "ROOT", "UNDEROVER", "big", "BIG", "color"}
KNOWN_WORDS = GREEK_ALL | SYMBOL_WORDS | BIG_OPS | FUNCS | DECOR | MATRIX | FONT_WORDS | STRUCT_WORDS

_LATEX_HINT = {
    "frac": "`{a} over {b}`", "sqrt": "`sqrt {x}`", "left": "`left ( ... right )`", "right": "`left ( ... right )`",
    "cdot": "`cdot`", "times": "`times`", "le": "`<=` 또는 `LEQ`", "leq": "`<=` 또는 `LEQ`", "ge": "`>=` 또는 `GEQ`",
    "geq": "`>=` 또는 `GEQ`", "neq": "`!=`", "ne": "`!=`", "infty": "`inf`", "int": "`int from {a} to {b}`",
    "sum": "`sum from {i=1} to {n}`", "begin": "`matrix{a & b # c & d}` / `cases{...}`",
    "text": '큰따옴표 `"글자"`', "mathrm": "`rm`", "pm": "`+-`", "overline": "`bar {x}`", "vec": "`vec {x}`",
}


@dataclass
class Finding:
    severity: str  # error | warning
    message: str


# ── 토큰 ──────────────────────────────────────────────────────────────
_TOKEN_RE = re.compile(
    r'"[^"]*"'                      # 따옴표 글자
    r"|\\[A-Za-z]+|\\."            # LaTeX 흔적
    r"|[A-Za-z]+"                   # 낱말
    r"|\d+(?:\.\d+)?"               # 숫자
    r"|<->|<=>|->|<-|<=|>=|!=|==|\+-|-\+|<<<|>>>|<<|>>|\.\.\."
    r"|[{}^_&#~`]"
    r"|\S",
)


def tokenize(script: str) -> List[str]:
    return _TOKEN_RE.findall(script.replace("\r", " ").replace("\n", " "))


# ── 검사 ──────────────────────────────────────────────────────────────
def check_script(script: str) -> List[Finding]:
    out: List[Finding] = []
    s = script.strip()
    if not s:
        return [Finding("error", "수식 스크립트가 비어 있습니다")]
    toks = tokenize(s)
    depth = 0
    for t in toks:
        if t == "{":
            depth += 1
        elif t == "}":
            depth -= 1
            if depth < 0:
                out.append(Finding("error", "닫는 중괄호 `}`가 여는 것보다 많습니다"))
                depth = 0
    if depth > 0:
        out.append(Finding("error", f"여는 중괄호 `{{`가 {depth}개 닫히지 않았습니다"))
    latex = [t for t in toks if t.startswith("\\") and len(t) > 1]
    for t in latex[:5]:
        word = t[1:]
        hint = _LATEX_HINT.get(word)
        msg = f"LaTeX 명령 `{t}` 가 있습니다 — 한글 수식 스크립트로 써 주세요"
        out.append(Finding("error", msg + (f" (예: {hint})" if hint else "")))
    if "$" in s:
        out.append(Finding("error", "`$` 기호는 쓰지 않습니다 (수식 스크립트만 적으세요)"))
    lower = [t for t in toks]
    n_left = sum(1 for t in lower if t in ("left", "LEFT"))
    n_right = sum(1 for t in lower if t in ("right", "RIGHT"))
    if n_left != n_right:
        out.append(Finding("error", f"`left`({n_left}개)와 `right`({n_right}개)의 짝이 맞지 않습니다"))
    for i, t in enumerate(toks):
        if t in ("over", "atop", "OVER"):
            if i == 0 or toks[i - 1] in ("{", "^", "_", "&", "#"):
                out.append(Finding("error", f"`{t}` 앞에 분자가 없습니다 (예: `{{a}} over {{b}}`)"))
            if i == len(toks) - 1 or toks[i + 1] in ("}", "&", "#"):
                out.append(Finding("error", f"`{t}` 뒤에 분모가 없습니다"))
        if t in ("root", "ROOT") and "of" not in toks[i + 1:i + 40]:
            out.append(Finding("error", "`root`는 `root {n} of {x}` 꼴로 씁니다 (제곱근은 `sqrt {x}`)"))
        if t in MATRIX and (i + 1 >= len(toks) or toks[i + 1] != "{"):
            out.append(Finding("error", f"`{t}` 뒤에는 `{{ ... }}` 가 와야 합니다"))
        if t in ("frac", "dfrac", "tfrac", "mathbf", "mathrm", "mathbb", "text", "begin", "end", "cdotp"):
            out.append(Finding("warning", f"`{t}`는 한글 수식 명령이 아닙니다 (LaTeX 습관?)"))
    return out


# ── 크기 추정 (em 단위 상자) ───────────────────────────────────────────
@dataclass
class Box:
    w: float
    asc: float
    desc: float

    @property
    def h(self) -> float:
        return self.asc + self.desc


_BASE_ASC, _BASE_DESC = 0.86, 0.14
_UPPER_W = dict(zip("ABCDEFGHIJKLMNOPQRSTUVWXYZ",
                    [.75, .614, .614, .68, .614, .56, .72, .72, .33, .39, .72, .614, .89, .72, .75, .614, .75,
                     .67, .56, .614, .72, .72, .94, .72, .72, .614]))
_NARROW = set("ijlrt")
_WIDE = set("mw")
_OPS = {"+", "-", "=", "<", ">", "<=", ">=", "!=", "==", "->", "<-", "<->", "<=>", "+-", "-+", "<<", ">>",
        "<<<", ">>>"}


def _char_w(ch: str) -> float:
    if ch.isdigit():
        return 0.477
    if ch in _UPPER_W:
        return _UPPER_W[ch]
    if "a" <= ch <= "z":
        return 0.3 if ch in _NARROW else 0.72 if ch in _WIDE else 0.477
    if ch in "()[]{}":
        return 0.55
    if ch in "|/\\":
        return 0.3
    if ch == ":":
        return 0.69
    if ch in ",.;'!":
        return 0.3
    if ord(ch) >= 0x1100:
        return 1.0
    return 0.55


def _text_box(s: str) -> Box:
    return Box(sum(_char_w(c) for c in s), _BASE_ASC, _BASE_DESC)


class _Parser:
    def __init__(self, toks: List[str]):
        self.toks = toks
        self.i = 0

    def peek(self, k: int = 0) -> Optional[str]:
        j = self.i + k
        return self.toks[j] if j < len(self.toks) else None

    def take(self) -> Optional[str]:
        t = self.peek()
        self.i += 1
        return t

    def expr(self, stop: Tuple[str, ...] = ("}",)) -> Box:
        items: List[Box] = []
        prev: Optional[str] = None
        while self.peek() is not None and self.peek() not in stop:
            t = self.peek()
            if t in ("over", "atop", "OVER") and items:
                self.take()
                num = items.pop()
                den = self.item()
                items.append(_frac(num, den))
                prev = "}"
                continue
            if t in ("+", "-", "+-", "-+") and (prev is None or prev in _OPS or prev in ("(", "{", "&", "#")
                                                or prev in SYMBOL_WORDS):
                self.take()
                items.append(self._scripts(Box(0.68, _BASE_ASC, _BASE_DESC)))
                prev = t
                continue
            if t not in ("~", "`"):
                prev = t
            items.append(self.item())
        return _hcat(items)

    def group_or_atom(self) -> Box:
        return self.item(scripts=False)

    def item(self, scripts: bool = True) -> Box:
        t = self.take()
        if t is None:
            return Box(0, _BASE_ASC, _BASE_DESC)
        if t == "{":
            b = self.expr(("}",))
            if self.peek() == "}":
                self.take()
        elif t in ("sqrt", "SQRT"):
            inner = self.group_or_atom()
            b = Box(inner.w + 1.17, inner.asc + 0.17, inner.desc)
            if self.peek() == "of":
                self.take()
                rad = self.group_or_atom()
                b = Box(inner.w * 0.6 + rad.w + 0.8, rad.asc + 0.17, rad.desc)
        elif t in ("root", "ROOT"):
            idx = self.group_or_atom()
            if self.peek() == "of":
                self.take()
            rad = self.group_or_atom()
            b = Box(idx.w * 0.6 + rad.w + 0.8, max(rad.asc + 0.17, idx.h * 0.6 + 0.4), rad.desc)
        elif t in ("left", "LEFT"):
            self.take()  # 여는 괄호
            inner = self.expr(("right", "RIGHT", "}"))
            if self.peek() in ("right", "RIGHT"):
                self.take()
                self.take()
            b = Box(inner.w + 1.1, inner.asc + 0.05, inner.desc + 0.05)
        elif t in BIG_OPS:
            b = self._big_op(t)
            return b
        elif t in MATRIX:
            b = self._matrix(t)
        elif t in DECOR:
            inner = self.group_or_atom()
            if t in ("under", "underline", "UNDERBRACE"):
                b = Box(inner.w, inner.asc, inner.desc + 0.2)
            else:
                b = Box(inner.w, inner.asc + 0.2, inner.desc)
        elif t in FONT_WORDS or t in ("color",):
            return Box(0, _BASE_ASC, _BASE_DESC)
        elif t == "~":
            b = Box(0.25, _BASE_ASC, _BASE_DESC)
        elif t == "`":
            b = Box(0.125, _BASE_ASC, _BASE_DESC)
        elif t in ("&", "#"):
            b = Box(0, _BASE_ASC, _BASE_DESC)
        elif t.startswith('"'):
            b = _text_box(t.strip('"'))
        elif t in FUNCS:
            b = Box(len(t) * 0.45 + 0.17, _BASE_ASC, _BASE_DESC)
        elif t in GREEK_ALL:
            b = Box(0.7 if t[0].isupper() else 0.55, _BASE_ASC, _BASE_DESC)
        elif t in ("CDOTS", "LDOTS", "cdots", "ldots", "...", "VDOTS", "DDOTS", "vdots", "ddots"):
            b = Box(1.0, _BASE_ASC, _BASE_DESC)
        elif t in _OPS or t in SYMBOL_WORDS:
            b = Box(0.98 if (t in _OPS and t not in ("-",)) or t.isupper() else 0.68, _BASE_ASC, _BASE_DESC)
        elif re.fullmatch(r"[A-Za-z]+", t):
            b = _text_box(t)
        else:
            b = _text_box(t)
        if not scripts:
            return b
        return self._scripts(b)

    def _scripts(self, base: Box) -> Box:
        sup: Optional[Box] = None
        sub: Optional[Box] = None
        while self.peek() in ("^", "_", "sup", "sub"):
            op = self.take()
            arg = self.group_or_atom()
            if op in ("^", "sup"):
                sup = arg
            else:
                sub = arg
        if sup is None and sub is None:
            return base
        k = 0.7
        w = base.w + max(sup.w * k if sup else 0, sub.w * k if sub else 0)
        asc, desc = base.asc, base.desc
        if sup is not None:
            shift = max(0.36, sup.desc * k + 0.3)
            asc = max(asc, shift + sup.asc * k)
        if sub is not None:
            shift = max(0.17, sub.asc * k - 0.45)
            desc = max(desc, shift + sub.desc * k + 0.07)
        return Box(w, asc, desc)

    def _big_op(self, t: str) -> Box:
        is_lim = t.lower() == "lim"
        is_int = "int" in t.lower()
        core = Box(len(t) * 0.45 if is_lim else (0.6 if is_int else 1.0), 1.0 if not is_lim else _BASE_ASC,
                   0.4 if not is_lim else _BASE_DESC)
        lower = upper = None
        while self.peek() in ("from", "to", "_", "^", "sub", "sup"):
            op = self.take()
            arg = self.group_or_atom()
            if op in ("from", "_", "sub"):
                lower = arg
            else:
                upper = arg
        k = 0.7
        if is_int:
            w = core.w + max(lower.w * k if lower else 0, upper.w * k if upper else 0)
            return Box(w + 0.1, core.asc + (0.1 if upper else 0), core.desc + (0.1 if lower else 0))
        w = max(core.w, lower.w * k if lower else 0, upper.w * k if upper else 0) + 0.17
        asc = core.asc + (upper.h * k + 0.1 if upper else 0)
        desc = core.desc + (lower.h * k + 0.1 if lower else 0)
        return Box(w, asc, desc)

    def _matrix(self, t: str) -> Box:
        if self.peek() != "{":
            return Box(1.0, _BASE_ASC, _BASE_DESC)
        self.take()
        rows: List[List[Box]] = [[]]
        cur: List[Box] = []
        while self.peek() is not None and self.peek() != "}":
            if self.peek() == "&":
                self.take()
                rows[-1].append(_hcat(cur))
                cur = []
                continue
            if self.peek() == "#":
                self.take()
                rows[-1].append(_hcat(cur))
                cur = []
                rows.append([])
                continue
            cur.append(self.item())
        rows[-1].append(_hcat(cur))
        if self.peek() == "}":
            self.take()
        ncols = max(len(r) for r in rows)
        colw = [max((r[c].w for r in rows if c < len(r)), default=0) for c in range(ncols)]
        gap = 0.3 if t in ("eqalign", "cases", "CASES") else 1.0
        w = sum(colw) + gap * (ncols - 1)
        h = sum(max((b.h for b in r), default=1.0) for r in rows) + 0.25 * (len(rows) - 1)
        if t in ("pmatrix", "bmatrix", "dmatrix"):
            w += 0.8
        elif t in ("cases", "CASES"):
            w += 0.6
        return Box(w, h / 2 + 0.25, h / 2 - 0.25)


def _hcat(items: List[Box]) -> Box:
    if not items:
        return Box(0, _BASE_ASC, _BASE_DESC)
    return Box(sum(b.w for b in items), max(b.asc for b in items), max(b.desc for b in items))


def _frac(num: Box, den: Box) -> Box:
    axis, gap = 0.25, 0.15
    return Box(max(num.w, den.w) + 0.5, axis + gap + num.h, den.h + gap - axis)


def estimate_size(script: str, base_unit: int) -> Tuple[int, int, int]:
    """(width, height, baseLine%) — HWPUNIT."""
    toks = tokenize(script)
    p = _Parser(toks)
    box = p.expr(stop=())
    while p.peek() is not None:  # 짝 안 맞는 `}` 등 남은 토큰
        p.take()
        rest = p.expr(stop=())
        box = _hcat([box, rest])
    w = max(box.w, 0.3)
    asc = max(box.asc, _BASE_ASC)
    desc = max(box.desc, _BASE_DESC)
    height = asc + desc
    return (int(round(w * base_unit)), int(round(height * base_unit)), int(round(asc / height * 100)))


# ── XML ────────────────────────────────────────────────────────────────
def equation_xml(script: str, base_unit: int, eq_id: int, z_order: int, hp: str = "hp",
                 color: str = "#000000", font: str = "HYhwpEQ") -> str:
    w, h, bl = estimate_size(script, base_unit)
    esc = xmlspan.escape_text(script)
    return (
        f'<{hp}:equation id="{eq_id}" zOrder="{z_order}" numberingType="EQUATION" textWrap="TOP_AND_BOTTOM" '
        f'textFlow="BOTH_SIDES" lock="0" dropcapstyle="None" version="Equation Version 60" baseLine="{bl}" '
        f'textColor="{color}" baseUnit="{int(base_unit)}" lineMode="CHAR" font="{font}">'
        f'<{hp}:sz width="{w}" widthRelTo="ABSOLUTE" height="{h}" heightRelTo="ABSOLUTE" protect="0"/>'
        f'<{hp}:pos treatAsChar="1" affectLSpacing="0" flowWithText="1" allowOverlap="0" holdAnchorAndSO="0" '
        f'vertRelTo="PARA" horzRelTo="PARA" vertAlign="TOP" horzAlign="LEFT" vertOffset="0" horzOffset="0"/>'
        f'<{hp}:outMargin left="56" right="56" top="0" bottom="0"/>'
        f'<{hp}:shapeComment>수식입니다.</{hp}:shapeComment>'
        f'<{hp}:script>{esc}</{hp}:script></{hp}:equation>'
    )


class ObjectIds:
    """섹션 안 개체 id·zOrder 발급기 (기존 최댓값 다음부터)."""

    def __init__(self, src: str):
        ids = [int(m.group(1)) for m in re.finditer(r'<\w+:(?:equation|tbl|pic|rect|ellipse|line|container|ole)'
                                                    r'\b[^>]*?\sid="(\d+)"', src)]
        zs = [int(m.group(1)) for m in re.finditer(r'\szOrder="(-?\d+)"', src)]
        self._id = max(ids + [1000000000]) + 1
        self._z = max(zs + [0]) + 1

    def next(self) -> Tuple[int, int]:
        out = (self._id, self._z)
        self._id += 1
        self._z += 1
        return out


# ── 문서의 수식 목록·교체 ───────────────────────────────────────────────
def list_equations(doc) -> List[Dict]:
    from .core.model import Section
    out: List[Dict] = []
    for si in range(len(doc.section_paths)):
        sec = Section(doc, si)
        for eq in sec.sec.iter("equation"):
            sc = eq.find("script")
            sz = eq.find("sz")
            p = eq.ancestor("p")
            out.append({
                "index": len(out),
                "section": si,
                "location": sec.paragraph_address(p) if p is not None else f"s{si}",
                "script": xmlspan.unescape(sc.inner(sec.src)) if sc is not None else "",
                "baseUnit": int(eq.get(sec.src, "baseUnit") or 1000),
                "width": int(sz.get(sec.src, "width") or 0) if sz is not None else 0,
                "height": int(sz.get(sec.src, "height") or 0) if sz is not None else 0,
            })
    return out


def replace_equation(doc, index: int, script: str, base_unit: Optional[int] = None) -> Dict:
    """index번째 수식의 스크립트를 바꾸고 크기를 다시 추정한다."""
    from .core.model import Section
    from .core.splice import Splice
    from .errors import HwpxError
    errs = [f for f in check_script(script) if f.severity == "error"]
    if errs:
        raise HwpxError("수식 스크립트 오류: " + "; ".join(f.message for f in errs))
    n = 0
    for si in range(len(doc.section_paths)):
        sec = Section(doc, si)
        for eq in sec.sec.iter("equation"):
            if n == index:
                src = sec.src
                bu = base_unit or int(eq.get(src, "baseUnit") or 1000)
                w, h, bl = estimate_size(script, bu)
                sp: List[Splice] = []
                tag = eq.open_tag(src)
                tag = xmlspan.set_attr(tag, "baseLine", str(bl))
                tag = xmlspan.set_attr(tag, "baseUnit", str(bu))
                sp.append(Splice(eq.start, eq.open_end, tag))
                sz = eq.find("sz")
                if sz is not None:
                    t2 = xmlspan.set_attr(xmlspan.set_attr(sz.open_tag(src), "width", str(w)), "height", str(h))
                    sp.append(Splice(sz.start, sz.open_end, t2))
                sc = eq.find("script")
                old = xmlspan.unescape(sc.inner(src)) if sc is not None else ""
                if sc is not None:
                    if sc.self_closing:
                        sp.append(Splice(sc.start, sc.end, f"<{sc.name}>{xmlspan.escape_text(script)}</{sc.name}>"))
                    else:
                        sp.append(Splice(sc.open_end, sc.close_start, xmlspan.escape_text(script)))
                doc.apply(sec.path, sp)
                return {"index": index, "old": old, "new": script, "width": w, "height": h}
            n += 1
    raise HwpxError(f"수식 {index}번이 없습니다 (수식 {n}개)")


_EQ_MARK_RE = re.compile(r"<eq(\s+block)?\s*>(.*?)</eq>", re.S)


def split_eq_markup(text: str) -> List[Tuple[str, str]]:
    """'글 <eq>x^2</eq> 글' → [('text','글 '), ('eq','x^2'), ('text',' 글')]. block 수식은 ('eqblock', …)."""
    out: List[Tuple[str, str]] = []
    pos = 0
    for m in _EQ_MARK_RE.finditer(text):
        if m.start() > pos:
            out.append(("text", text[pos:m.start()]))
        out.append(("eqblock" if m.group(1) else "eq", m.group(2).strip()))
        pos = m.end()
    if pos < len(text):
        out.append(("text", text[pos:]))
    return out


def has_eq_markup(text: str) -> bool:
    return bool(_EQ_MARK_RE.search(text))
