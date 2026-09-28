"""서식을 갖춘 내용 쓰기 — 양식의 예시 서식을 익혀 새 내용에 입힌다.

입력은 Claude가 쓴 일반 텍스트 줄이다. 줄 앞의 항목부호(□ ○ - · ※ 1. 가. 1) 가) (1) (가) ① ㉮ …)로
단계를 나타내며 마크다운 강조 문법은 쓰지 않는다. `<eq>한글 수식</eq>`은 인라인 수식,
`<eq block>…</eq>`는 가운데 정렬한 독립 줄 수식이 된다.

서식 출처 우선순위
1. 같은 자리(셀·누름틀·자리표시 문단)에 예시로 들어 있던 문단 — 부호별로 문단 모양·글자 모양을 익힌다.
2. 같은 표의 다른 셀에 있는 예시 문단.
3. 예시가 없으면 첫 문단 서식을 그대로 쓰고, 단계마다 들여쓰기·내어쓰기를 더한 문단 모양을
   만든다. 부호 뒤에 자동 탭(내어쓰기 위치)을 두어 둘째 줄이 부호 뒤 글자에 맞춰진다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from .core import xmlspan
from .core.splice import Splice
from .core.text import ParaText, inline_xml, paragraph_has_objects
from .equation import ObjectIds, equation_xml, split_eq_markup

# (정규식, 부호 종류)
_MARKERS: List[Tuple[str, str]] = [
    (r"\(\d{1,2}\)", "(1)"), (r"\([가-하]\)", "(가)"),
    (r"\d{1,2}\)", "1)"), (r"[가-하]\)", "가)"),
    (r"\d{1,2}\.(?!\d)", "1."), (r"[가-하]\.", "가."),
    (r"[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ]\.", "Ⅰ."), (r"[ㄱ-ㅎ]\.", "ㄱ."),
    (r"[①-⑳]", "①"), (r"[㉮-㉻]", "㉮"), (r"[㉠-㉭]", "㉠"),
    (r"□", "□"), (r"■", "■"), (r"[○◯]", "○"), (r"❍", "❍"), (r"ㅇ(?=\s)", "ㅇ"), (r"●", "●"),
    (r"◦", "◦"), (r"◆", "◆"), (r"◇", "◇"), (r"▪", "▪"), (r"[▶►]", "▶"), (r"[-–]", "-"),
    (r"[·ㆍ∙•]", "·"), (r"※", "※"), (r"\*", "*"), (r"⇒|=>|→", "⇒"),
]
_SYMBOL_CLASSES = {"□", "■", "○", "❍", "ㅇ", "●", "◦", "◆", "◇", "▪", "▶", "-", "·", "※", "*", "⇒",
                   "①", "㉮", "㉠"}
_MARKER_RE = re.compile(
    r"^(?P<lead>[ \t　]*)(?P<marker>" + "|".join(f"(?:{p})" for p, _ in _MARKERS) + r")(?P<sep>[ \t　]*)")
# 공문서 항목 체계 (행정업무운영 편람) / 개조식 보고서 체계
_FAMILY_LEGAL = ["1.", "가.", "1)", "가)", "(1)", "(가)", "①", "㉮"]
_FAMILY_REPORT = ["Ⅰ.", "□", "■", "○", "❍", "ㅇ", "●", "-", "◦", "·", "*"]
_HEAD_RE = re.compile(r"^(\([^()]{1,12}\)|\[[^\[\]]{1,12}\]|「[^「」]{1,20}」|<[^<>]{1,12}>|[^\s:：]{1,12}[:：])")


def marker_class(marker: str) -> str:
    for pat, cls in _MARKERS:
        if re.fullmatch(pat, marker):
            return cls
    return marker


@dataclass
class Line:
    raw: str
    lead: str
    marker: str
    mclass: str
    sep: str
    body: str
    level: int = 0
    block_eq: Optional[str] = None


def parse_lines(value: str) -> List[Line]:
    """값을 줄 목록으로. 부호가 없는 줄은 mclass=''."""
    out: List[Line] = []
    for raw in value.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        m = _MARKER_RE.match(raw)
        # 부호 뒤에는 공백·탭이 있어야 한다 ('○○부'·'1.5배' 같은 글자는 부호가 아님)
        sep_ok = m is not None and (bool(m.group("sep")) or m.end() == len(raw))
        if m and sep_ok:
            mk = m.group("marker")
            out.append(Line(raw, m.group("lead"), mk, marker_class(mk), m.group("sep"), raw[m.end():]))
        else:
            stripped = raw.lstrip(" \t　")
            lead = raw[:len(raw) - len(stripped)]
            ln = Line(raw, lead, "", "", "", stripped)
            parts = split_eq_markup(stripped)
            if len(parts) == 1 and parts[0][0] == "eqblock":
                ln.block_eq = parts[0][1]
            out.append(ln)
    _assign_levels(out)
    return out


def _assign_levels(lines: List[Line]) -> None:
    present = {ln.mclass for ln in lines if ln.mclass}
    fam_min: Dict[str, int] = {}
    for fam_name, fam in (("legal", _FAMILY_LEGAL), ("report", _FAMILY_REPORT)):
        ranks = [fam.index(c) for c in present if c in fam]
        if ranks:
            fam_min[fam_name] = min(ranks)
    order: List[str] = []
    prev_level = 0
    for ln in lines:
        c = ln.mclass
        if not c:
            ln.level = prev_level if ln.lead else 0
            continue
        if c in _FAMILY_LEGAL:
            ln.level = _FAMILY_LEGAL.index(c) - fam_min.get("legal", 0)
        elif c in _FAMILY_REPORT:
            rank = _distinct_rank(c, present, _FAMILY_REPORT)
            ln.level = rank
        elif c == "※":
            ln.level = prev_level + 1
        else:
            if c not in order:
                order.append(c)
            ln.level = order.index(c)
        prev_level = ln.level


def _distinct_rank(c: str, present: set, fam: List[str]) -> int:
    used = [x for x in fam if x in present]
    # 같은 층위로 쓰이는 이형(□/■, ○/❍/ㅇ/●)은 한 단계로 묶는다
    groups = [{"Ⅰ."}, {"□", "■"}, {"○", "❍", "ㅇ", "●"}, {"-", "◦"}, {"·", "*"}]
    levels: List[set] = []
    for x in used:
        g = next((g for g in groups if x in g), {x})
        if g not in levels:
            levels.append(g)
    for i, g in enumerate(levels):
        if c in g:
            return i
    return 0


# ── 서식 원형 ────────────────────────────────────────────────────────────
@dataclass
class Proto:
    p_tag: str
    parapr: int
    marker_cp: int
    body_cp: int
    head_cp: Optional[int] = None
    lead: str = ""
    sep: str = " "
    use_tab: bool = False
    tab_width: int = 0
    source: str = "example"


class StyleBook:
    """자리 하나의 서식 원형 모음."""

    def __init__(self, doc, src: str, base_p: xmlspan.Node, examples: Sequence[xmlspan.Node] = (),
                 base_cp: Optional[int] = None, extra_examples: Sequence[xmlspan.Node] = ()):
        self.doc = doc
        self.src = src
        self.header = doc.header
        self.base_tag = base_p.open_tag(src)
        self.base_parapr = int(base_p.get(src, "paraPrIDRef") or 0)
        pt = ParaText(src, base_p)
        if base_cp is None:
            run = pt.run_at(0) if pt.text else (pt.runs[0] if pt.runs else None)
            base_cp = int(run.get(src, "charPrIDRef") or 0) if run is not None else 0
        self.base_cp = base_cp
        self.by_class: Dict[str, Proto] = {}
        self.plain: Optional[Proto] = None
        for p in list(examples) + list(extra_examples):
            self._learn(p)
        self._derived: Dict[Tuple[str, int], Proto] = {}
        self._auto_tab: Optional[int] = None

    def _learn(self, p: xmlspan.Node) -> None:
        src = self.src
        pt = ParaText(src, p)
        text = pt.text
        if not text.strip():
            return
        m = _MARKER_RE.match(text)
        tag = p.open_tag(src)
        parapr = int(p.get(src, "paraPrIDRef") or 0)
        if not m or not m.group("sep"):
            if self.plain is None:
                run = pt.run_at(len(text) - len(text.lstrip()))
                cp = int(run.get(src, "charPrIDRef") or 0) if run is not None else self.base_cp
                self.plain = Proto(tag, parapr, cp, cp, source="example")
            return
        cls = marker_class(m.group("marker"))
        if cls in self.by_class:
            return
        lead, sep = m.group("lead"), m.group("sep")
        mk_run = pt.run_at(len(lead))
        mk_cp = int(mk_run.get(src, "charPrIDRef") or 0) if mk_run is not None else self.base_cp
        body_at = m.end()
        body_run = pt.run_at(min(body_at, len(text) - 1)) if body_at < len(text) else mk_run
        body_cp = int(body_run.get(src, "charPrIDRef") or 0) if body_run is not None else mk_cp
        head_cp = None
        hm = _HEAD_RE.match(text[body_at:])
        if hm:
            h_run = pt.run_at(body_at)
            after = body_at + hm.end()
            rest = text[after:].lstrip()
            r_run = pt.run_at(len(text) - len(rest)) if rest else None
            if h_run is not None and r_run is not None and h_run is not r_run:
                hc = int(h_run.get(src, "charPrIDRef") or 0)
                rc = int(r_run.get(src, "charPrIDRef") or 0)
                if hc != rc:
                    head_cp, body_cp = hc, rc
        self.by_class[cls] = Proto(tag, parapr, mk_cp, body_cp, head_cp, lead, sep or "", "\t" in sep)

    # ── 원형 고르기 ──
    def proto_for(self, line: Line) -> Proto:
        if line.block_eq is not None:
            return self._center()
        if not line.mclass:
            if line.lead and line.level > 0:
                return self._continuation(line.level)
            return self.plain or Proto(self.base_tag, self.base_parapr, self.base_cp, self.base_cp,
                                       source="base")
        if line.mclass in self.by_class:
            return self.by_class[line.mclass]
        return self._derive(line)

    def _base_margin_left(self) -> int:
        return self.header.parapr(self.base_parapr)["margin"]["left"]

    def _em(self) -> int:
        try:
            return int(self.header.charpr(self.base_cp)["height"])
        except Exception:
            return 1000

    def _derive(self, line: Line) -> Proto:
        key = (line.mclass, line.level)
        if key in self._derived:
            return self._derived[key]
        em = self._em()
        marker_w = int(_text_width_em(line.marker) * em)
        hang = marker_w + em // 2
        left = self._base_margin_left() + line.level * em + hang
        if self._auto_tab is None:
            self._auto_tab = self.header.ensure_auto_tab()
        parapr = self.header.derive_parapr(self.base_parapr, left=left, intent=-hang, tab_pr=self._auto_tab,
                                           no_heading=True)
        proto = Proto(self.base_tag, parapr, self.base_cp, self.base_cp, None, "", "\t", True,
                      max(hang - marker_w, 100), source="derived")
        self._derived[key] = proto
        return proto

    def _continuation(self, level: int) -> Proto:
        key = ("", level)
        if key in self._derived:
            return self._derived[key]
        em = self._em()
        left = self._base_margin_left() + level * em + int(1.5 * em)
        parapr = self.header.derive_parapr(self.base_parapr, left=left, intent=0, no_heading=True)
        proto = Proto(self.base_tag, parapr, self.base_cp, self.base_cp, source="derived")
        self._derived[key] = proto
        return proto

    def _center(self) -> Proto:
        key = ("<eq>", 0)
        if key not in self._derived:
            parapr = self.header.derive_parapr(self.base_parapr, align="CENTER", left=self._base_margin_left(),
                                               intent=0, no_heading=True)
            self._derived[key] = Proto(self.base_tag, parapr, self.base_cp, self.base_cp, source="derived")
        return self._derived[key]


def _text_width_em(s: str) -> float:
    w = 0.0
    for ch in s:
        if ch in "()[]":
            w += 0.33
        elif ch in ".,":
            w += 0.3
        elif ch.isascii():
            w += 0.55
        else:
            w += 1.0
    return w


# ── XML 만들기 ───────────────────────────────────────────────────────────
@dataclass
class WriteContext:
    doc: object
    src: str
    hp: str = "hp"
    ids: Optional[ObjectIds] = None
    notes: List[str] = field(default_factory=list)

    def eq_ids(self) -> ObjectIds:
        if self.ids is None:
            self.ids = ObjectIds(self.src)
        return self.ids

    def base_unit(self, cp: int) -> int:
        try:
            return int(self.doc.header.charpr(cp)["height"])
        except Exception:
            return 1000


def run_content(ctx: WriteContext, text: str, cp: int) -> str:
    """run 안쪽 XML: 글자는 hp:t, `<eq>` 수식은 hp:equation."""
    hp = ctx.hp
    parts = split_eq_markup(text)
    out: List[str] = []
    for kind, val in parts:
        if kind == "text":
            if val:
                out.append(f"<{hp}:t>{inline_xml(val, hp)}</{hp}:t>")
        else:
            eid, z = ctx.eq_ids().next()
            out.append(equation_xml(val, ctx.base_unit(cp), eid, z, hp))
    if not out:
        out.append(f"<{hp}:t/>")
    elif not out[-1].startswith(f"<{hp}:t"):
        out.append(f"<{hp}:t/>")
    return "".join(out)


def line_runs(ctx: WriteContext, proto: Proto, line: Line) -> str:
    hp = ctx.hp
    runs: List[Tuple[int, str]] = []
    if line.block_eq is not None:
        return f'<{hp}:run charPrIDRef="{proto.body_cp}">{run_content(ctx, "<eq>" + line.block_eq + "</eq>", proto.body_cp)}</{hp}:run>'
    body = line.body
    if line.mclass:
        lead = proto.lead if proto.source == "example" else ""
        if proto.use_tab:
            mk = f"<{hp}:t>{xmlspan.escape_text(lead + line.marker)}<{hp}:tab width=\"{proto.tab_width or 1000}\" leader=\"0\" type=\"1\"/></{hp}:t>"
        else:
            sep = proto.sep if proto.source == "example" else (line.sep or " ")
            mk = f"<{hp}:t>{inline_xml(lead + line.marker + (sep or ' '), hp)}</{hp}:t>"
        runs.append((proto.marker_cp, mk))
        hm = _HEAD_RE.match(body) if proto.head_cp is not None else None
        if hm:
            runs.append((proto.head_cp, run_content(ctx, hm.group(0), proto.head_cp)))
            body = body[hm.end():]
        if body:
            runs.append((proto.body_cp, run_content(ctx, body, proto.body_cp)))
    else:
        runs.append((proto.body_cp, run_content(ctx, line.body, proto.body_cp)))
    merged: List[Tuple[int, str]] = []
    for cp, x in runs:
        if merged and merged[-1][0] == cp:
            merged[-1] = (cp, merged[-1][1] + x)
        else:
            merged.append((cp, x))
    return "".join(f'<{hp}:run charPrIDRef="{cp}">{x}</{hp}:run>' for cp, x in merged)


def paragraph_open(proto: Proto) -> str:
    tag = xmlspan.set_attr(proto.p_tag, "paraPrIDRef", str(proto.parapr))
    for k in ("pageBreak", "columnBreak"):
        if xmlspan.get_attr(tag, k) not in (None, "0"):
            tag = xmlspan.set_attr(tag, k, "0")
    return tag


def paragraph_xml(ctx: WriteContext, proto: Proto, line: Line, p_name: str) -> str:
    return paragraph_open(proto) + line_runs(ctx, proto, line) + f"</{p_name}>"


def is_rich(value: str) -> bool:
    """여러 문단·항목부호·수식이 있는 값인지 (그렇지 않으면 글자만 바꾼다)."""
    return "\n" in value or "<eq block" in value


# ── 자리별 쓰기 ──────────────────────────────────────────────────────────
def write_paragraphs(ctx: WriteContext, book: StyleBook, lines: List[Line], p_name: str) -> str:
    return "".join(paragraph_xml(ctx, book.proto_for(ln), ln, p_name) for ln in lines)


def cell_splices(ctx: WriteContext, cell, value: str, extra_examples: Sequence[xmlspan.Node] = ()) -> List[Splice]:
    """셀 내용 전체를 value로 바꾼다. 셀 안에 표·그림 같은 개체가 있으면 첫 글자 문단만 바꾼다."""
    src = ctx.src
    paras = cell.paragraphs()
    if not paras:
        ctx.notes.append(f"{cell.address}: 셀에 문단이 없어 건너뜀")
        return []
    if any(paragraph_has_objects(p) for p in paras):
        target = next((p for p in paras if ParaText(src, p).text.strip()), paras[0])
        ctx.notes.append(f"{cell.address}: 셀에 개체(표·그림 등)가 있어 첫 글자 문단만 바꿈")
        return ParaText(src, target).set_text(_flat_inline(ctx, value))
    base = next((p for p in paras if ParaText(src, p).text.strip()), paras[0])
    book = StyleBook(ctx.doc, src, base, paras, extra_examples=extra_examples)
    lines = parse_lines(value)
    xml = write_paragraphs(ctx, book, lines, paras[0].name)
    return [Splice(paras[0].start, paras[-1].end, xml)]


def _flat_inline(ctx: WriteContext, value: str) -> str:
    return inline_xml(value.replace("<eq>", "").replace("</eq>", ""), ctx.hp)


def chain_at(p: xmlspan.Node, pos: int) -> List[xmlspan.Node]:
    """문단 p 안에서 원문 위치 pos를 감싸고 있는 요소 사슬 (바깥→안쪽)."""
    chain: List[xmlspan.Node] = []
    node = p
    while True:
        nxt = None
        for c in node.children:
            if not c.self_closing and c.open_end <= pos <= c.close_start:
                nxt = c
                break
        if nxt is None:
            return chain
        chain.append(nxt)
        node = nxt


def range_splices(ctx: WriteContext, p_a: xmlspan.Node, a: int, p_b: xmlspan.Node, b: int, value: str,
                  book: StyleBook, head_override: Optional[Tuple[int, int, str]] = None) -> List[Splice]:
    """문단 p_a의 위치 a ~ 문단 p_b의 위치 b 사이를 value 내용으로 바꾼다 (여러 문단으로 늘어날 수 있다).

    교체 범위는 [a, b)뿐이다: a에서 열린 요소를 닫고 새 run·문단을 넣은 뒤 b의 요소를 다시 연다.
    head_override=(start, end, 새 태그)는 a 앞의 태그 하나(누름틀 시작 등)를 함께 고칠 때 쓴다.
    """
    src = ctx.src
    lines = parse_lines(value) or [Line("", "", "", "", "", "")]
    ca, cb = chain_at(p_a, a), chain_at(p_b, b)
    out: List[Splice] = []
    if head_override is not None:
        out.append(Splice(head_override[0], head_override[1], head_override[2]))
    single = len(lines) == 1 and lines[0].block_eq is None
    if single and len(ca) == 1 and ca == cb and ca[0].local == "run":
        run = ca[0]
        cp = int(run.get(src, "charPrIDRef") or 0)
        ln = lines[0]
        text = ln.raw.strip() if ln.mclass else ln.body
        out.append(Splice(a, b, run_content(ctx, text, cp)))
        return out
    close_a = "".join(f"</{n.name}>" for n in reversed(ca))
    reopen_b = "".join(n.open_tag(src) for n in cb)
    # a 앞·b 뒤에 글자가 없으면(자리가 문단 전체) 첫 줄 문단 모양을 p_a에 입힌다
    if not _text_before(src, p_a, a).strip() and not _text_after(src, p_b, b).strip():
        proto1 = book.proto_for(lines[0])
        tag = p_a.open_tag(src)
        new_tag = xmlspan.set_attr(tag, "paraPrIDRef", str(proto1.parapr))
        if new_tag != tag:
            if head_override is not None and head_override[0] < p_a.open_end:
                pass
            else:
                out.append(Splice(p_a.start, p_a.open_end, new_tag))
    first = line_runs(ctx, book.proto_for(lines[0]), lines[0])
    if len(lines) == 1:
        out.append(Splice(a, b, close_a + first + reopen_b))
        return out
    mids = "".join(paragraph_xml(ctx, book.proto_for(ln), ln, p_a.name) for ln in lines[1:-1])
    last_proto = book.proto_for(lines[-1])
    last = paragraph_open(last_proto) + line_runs(ctx, last_proto, lines[-1])
    out.append(Splice(a, b, close_a + first + f"</{p_a.name}>" + mids + last + reopen_b))
    return out


def _text_after(src: str, p: xmlspan.Node, pos: int) -> str:
    pt = ParaText(src, p)
    out = []
    for seg in pt.segs:
        if seg.rs >= pos:
            out.append(seg.text)
        elif seg.re > pos and seg.kind == "txt":
            out.append(seg.text[pos - seg.rs:])
    return "".join(out)


def _text_before(src: str, p: xmlspan.Node, pos: int) -> str:
    pt = ParaText(src, p)
    out = []
    for seg in pt.segs:
        if seg.re <= pos:
            out.append(seg.text)
        elif seg.rs < pos and seg.kind == "txt":
            out.append(seg.text[:pos - seg.rs])
    return "".join(out)
