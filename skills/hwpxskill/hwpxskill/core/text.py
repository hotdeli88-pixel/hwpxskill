"""문단 글자 모델.

문단(`hp:p`)이 직접 가진 run → `hp:t`의 글자를 이어 붙인 '글자 영역'과 원문 위치를
대응시킨다. 글자 서식 때문에 여러 run으로 쪼개진 `{{키}}`, 줄바꿈(`hp:lineBreak`) 뒤 글자도
하나의 문자열로 보고 찾은 뒤, 원문의 해당 `hp:t` 안쪽만 부분 교체한다.
"""
from __future__ import annotations

import re
from typing import List, Optional, Tuple

from . import xmlspan
from .splice import Splice

INLINE_CHAR = {"lineBreak": "\n", "tab": "\t", "nbSpace": " ", "fwSpace": " ", "hwSpace": " "}
_CHUNK_RE = re.compile(r"&(?:#x[0-9A-Fa-f]+|#\d+|[A-Za-z]+);|<!\[CDATA\[(.*?)\]\]>", re.S)
# 문단 글자로 보지 않는 run 자식 (표·그림·수식 등은 자기 문단을 따로 가진다)
OBJECT_TAGS = frozenset({"tbl", "pic", "equation", "rect", "ellipse", "line", "arc", "polygon", "curve",
                         "connectLine", "container", "ole", "chart", "video", "textart", "compose", "dutmal",
                         "btn", "radioBtn", "checkBtn", "comboBox", "edit", "listBox", "scrollBar"})


class Seg:
    __slots__ = ("kind", "rs", "re", "tstart", "text", "t", "run", "cdata")

    def __init__(self, kind: str, rs: int, re_: int, tstart: int, text: str, t: xmlspan.Node,
                 run: xmlspan.Node, cdata: bool = False):
        self.kind = kind  # txt | ent | el
        self.rs = rs
        self.re = re_
        self.tstart = tstart
        self.text = text
        self.t = t
        self.run = run
        self.cdata = cdata

    @property
    def tend(self) -> int:
        return self.tstart + len(self.text)


class ParaText:
    """문단 하나의 글자 영역."""

    def __init__(self, src: str, p: xmlspan.Node):
        self.src = src
        self.p = p
        self.segs: List[Seg] = []
        self.runs: List[xmlspan.Node] = p.findall("run")
        self.t_nodes: List[xmlspan.Node] = []
        parts: List[str] = []
        pos = 0
        for run in self.runs:
            for child in run.children:
                if child.local != "t":
                    continue
                self.t_nodes.append(child)
                for seg in _t_segments(src, child, run):
                    seg.tstart = pos
                    pos += len(seg.text)
                    parts.append(seg.text)
                    self.segs.append(seg)
        self.text = "".join(parts)

    # ── 위치 ──
    def raw_pos(self, i: int) -> Optional[Tuple[int, Seg]]:
        """글자 위치 i 앞에 삽입할 원문 위치와 그 조각."""
        last = None
        for seg in self.segs:
            if not seg.text:
                last = seg
                continue
            if seg.tstart <= i < seg.tend:
                if seg.kind == "txt":
                    return seg.rs + (i - seg.tstart), seg
                return seg.rs, seg
            last = seg
        if last is not None and i >= len(self.text):
            return last.re, last
        return None

    def run_at(self, i: int) -> Optional[xmlspan.Node]:
        for seg in self.segs:
            if seg.text and seg.tstart <= i < seg.tend:
                return seg.run
        return self.runs[0] if self.runs else None

    # ── 편집 ──
    def replace(self, start: int, end: int, value_xml: str) -> List[Splice]:
        """글자 [start, end)를 value_xml(이미 이스케이프된 인라인 XML)로 바꾸는 교체 목록."""
        dels: List[Tuple[int, int, bool]] = []
        for seg in self.segs:
            if not seg.text:
                continue
            a = max(start, seg.tstart)
            b = min(end, seg.tend)
            if a >= b:
                continue
            if seg.kind == "txt":
                dels.append((seg.rs + (a - seg.tstart), seg.rs + (b - seg.tstart), seg.cdata))
            else:
                dels.append((seg.rs, seg.re, False))
        at = self.raw_pos(start)
        if at is None:
            return self.insert_new_t(value_xml)
        pos, seg = at
        ins = value_xml
        if seg.cdata and seg.kind == "txt" and seg.rs <= pos <= seg.re and value_xml:
            ins = "]]>" + value_xml + "<![CDATA["
        out: List[Splice] = []
        merged = False
        for a, b, _ in dels:
            if not merged and a == pos:
                out.append(Splice(a, b, ins))
                merged = True
            else:
                out.append(Splice(a, b, ""))
        if not merged and ins:
            out.append(Splice(pos, pos, ins))
        return out

    def insert_new_t(self, value_xml: str) -> List[Splice]:
        """글자가 전혀 없는 문단에 글자를 넣는다."""
        if not value_xml:
            return []
        src = self.src
        for t in self.t_nodes:
            if t.self_closing:
                return [Splice(t.start, t.end, f"<{t.name}>{value_xml}</{t.name}>")]
            return [Splice(t.open_end, t.open_end, value_xml)]
        hp = self.p.prefix + ":" if self.p.prefix else ""
        for run in self.runs:
            if run.self_closing:
                opened = run.open_tag(src)[:-2].rstrip() + ">"
                return [Splice(run.start, run.end, f"{opened}<{hp}t>{value_xml}</{hp}t></{run.name}>")]
            if not any(c.local in OBJECT_TAGS or c.local in ("ctrl", "secPr") for c in run.children):
                return [Splice(run.close_start, run.close_start, f"<{hp}t>{value_xml}</{hp}t>")]
        if self.runs:
            run = self.runs[-1]
            if run.self_closing:
                opened = run.open_tag(src)[:-2].rstrip() + ">"
                return [Splice(run.start, run.end, f"{opened}<{hp}t>{value_xml}</{hp}t></{run.name}>")]
            return [Splice(run.close_start, run.close_start, f"<{hp}t>{value_xml}</{hp}t>")]
        pos = _before_lineseg(self.p)
        return [Splice(pos, pos, f'<{hp}run charPrIDRef="0"><{hp}t>{value_xml}</{hp}t></{hp}run>')]

    def set_text(self, value_xml: str) -> List[Splice]:
        """문단 글자 전체를 바꾼다 (run 구조·다른 run의 빈 hp:t는 그대로 둔다)."""
        return self.replace(0, len(self.text), value_xml)


def _before_lineseg(p: xmlspan.Node) -> int:
    ls = p.find("linesegarray")
    return ls.start if ls is not None else p.close_start


def _t_segments(src: str, t: xmlspan.Node, run: xmlspan.Node) -> List[Seg]:
    segs: List[Seg] = []
    if t.self_closing:
        return segs
    pos = t.open_end
    for child in t.children:
        segs.extend(_text_chunk(src, pos, child.start, t, run))
        segs.append(Seg("el", child.start, child.end, 0, INLINE_CHAR.get(child.local, ""), t, run))
        pos = child.end
    segs.extend(_text_chunk(src, pos, t.close_start, t, run))
    return segs


def _text_chunk(src: str, a: int, b: int, t: xmlspan.Node, run: xmlspan.Node) -> List[Seg]:
    out: List[Seg] = []
    pos = a
    for m in _CHUNK_RE.finditer(src, a, b):
        if m.start() > pos:
            out.append(Seg("txt", pos, m.start(), 0, src[pos:m.start()], t, run))
        if m.group(0).startswith("&"):
            out.append(Seg("ent", m.start(), m.end(), 0, xmlspan.unescape(m.group(0)), t, run))
        else:
            ia, ib = m.start(1), m.end(1)
            if ib > ia:
                out.append(Seg("txt", ia, ib, 0, src[ia:ib], t, run, cdata=True))
        pos = m.end()
    if b > pos:
        out.append(Seg("txt", pos, b, 0, src[pos:b], t, run))
    return out


def inline_xml(text: str, hp: str = "hp") -> str:
    """일반 글자를 hp:t 안에 넣을 XML로. 줄바꿈→lineBreak, 탭→tab."""
    out = []
    for i, line in enumerate(text.split("\n")):
        if i:
            out.append(f"<{hp}:lineBreak/>")
        pieces = line.split("\t")
        for j, piece in enumerate(pieces):
            if j:
                out.append(f'<{hp}:tab width="4000" leader="0" type="1"/>')
            out.append(xmlspan.escape_text(piece))
    return "".join(out)


def paragraph_text(src: str, p: xmlspan.Node) -> str:
    return ParaText(src, p).text


def paragraph_has_objects(p: xmlspan.Node) -> bool:
    """문단에 표·그림·수식·컨트롤 같은 글자 아닌 요소가 있는지."""
    for run in p.findall("run"):
        for c in run.children:
            if c.local in OBJECT_TAGS or c.local in ("ctrl", "secPr"):
                return True
    return False
