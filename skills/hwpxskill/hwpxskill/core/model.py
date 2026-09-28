"""섹션·표·셀·문단 탐색과 주소.

주소 규칙 (analyze 출력과 fill 입력이 같은 규칙을 쓴다)
- 표: `s{섹션}.t{표번호}` — 섹션 안에서 문서 순서(바깥 표 → 그 안의 표) 0부터
- 셀: `s0.t1.r{행}.c{열}` — 셀 주소(cellAddr) 기준, 병합 셀은 왼쪽 위 칸 주소
- 본문 문단: `s0.p{번호}` — 섹션 최상위 문단 0부터
- 셀 문단: `s0.t1.r2.c1.p0`
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, Iterator, List, Optional, Tuple

from ..errors import HwpxError
from . import xmlspan
from .text import ParaText


def _int(v: Optional[str], default: int = 0) -> int:
    try:
        return int(v) if v is not None else default
    except ValueError:
        return default


@dataclass
class Cell:
    tc: xmlspan.Node
    table: "Table"
    row: int
    col: int
    rowspan: int
    colspan: int
    width: int
    height: int
    tr_index: int
    tc_index: int

    @property
    def address(self) -> str:
        return f"{self.table.id}.r{self.row}.c{self.col}"

    @property
    def sublist(self) -> Optional[xmlspan.Node]:
        return self.tc.find("subList")

    def paragraphs(self) -> List[xmlspan.Node]:
        sl = self.sublist
        return sl.findall("p") if sl is not None else []

    def text(self, src: str) -> str:
        return "\n".join(ParaText(src, p).text for p in self.paragraphs())

    def has_nested_table(self) -> bool:
        for p in self.paragraphs():
            for run in p.findall("run"):
                if run.find("tbl") is not None:
                    return True
        return False

    def border_fill(self, src: str) -> int:
        return _int(self.tc.get(src, "borderFillIDRef"), 0)


@dataclass
class Table:
    node: xmlspan.Node
    section: int
    index: int
    parent_cell: Optional[str] = None
    _cells: Optional[List[Cell]] = field(default=None, repr=False)

    @property
    def id(self) -> str:
        return f"s{self.section}.t{self.index}"

    def rows(self) -> List[xmlspan.Node]:
        return self.node.findall("tr")

    def cells(self, src: str) -> List[Cell]:
        if self._cells is None:
            out: List[Cell] = []
            for ri, tr in enumerate(self.rows()):
                for ci, tc in enumerate(tr.findall("tc")):
                    addr = tc.find("cellAddr")
                    span = tc.find("cellSpan")
                    sz = tc.find("cellSz")
                    row = _int(addr.get(src, "rowAddr"), ri) if addr is not None else ri
                    col = _int(addr.get(src, "colAddr"), ci) if addr is not None else ci
                    out.append(Cell(
                        tc, self, row, col,
                        _int(span.get(src, "rowSpan"), 1) if span is not None else 1,
                        _int(span.get(src, "colSpan"), 1) if span is not None else 1,
                        _int(sz.get(src, "width"), 0) if sz is not None else 0,
                        _int(sz.get(src, "height"), 0) if sz is not None else 0,
                        ri, ci))
            self._cells = out
        return self._cells

    def row_count(self, src: str) -> int:
        rc = self.node.get(src, "rowCnt")
        return _int(rc, len(self.rows())) if rc else len(self.rows())

    def col_count(self, src: str) -> int:
        cc = self.node.get(src, "colCnt")
        if cc:
            return _int(cc, 0)
        cells = self.cells(src)
        return max((c.col + c.colspan for c in cells), default=0)

    def cell(self, src: str, row: int, col: int) -> Optional[Cell]:
        """(row, col)을 덮는 셀 (병합 셀이면 그 병합 셀)."""
        for c in self.cells(src):
            if c.row <= row < c.row + c.rowspan and c.col <= col < c.col + c.colspan:
                return c
        return None

    def row_cells(self, src: str, tr_index: int) -> List[Cell]:
        return [c for c in self.cells(src) if c.tr_index == tr_index]

    def grid_text(self, src: str, max_len: int = 40) -> List[List[str]]:
        rows, cols = self.row_count(src), self.col_count(src)
        grid = [["" for _ in range(cols)] for _ in range(rows)]
        for c in self.cells(src):
            if c.row < rows and c.col < cols:
                t = c.text(src).replace("\n", " / ")
                grid[c.row][c.col] = t if len(t) <= max_len else t[:max_len - 1] + "…"
                for dr in range(c.rowspan):
                    for dc in range(c.colspan):
                        if (dr or dc) and c.row + dr < rows and c.col + dc < cols:
                            grid[c.row + dr][c.col + dc] = "〃"
        return grid


class Section:
    """섹션 파트 하나. 편집 후에는 새로 만들어 써야 한다 (위치가 바뀌므로)."""

    def __init__(self, doc, index: int):
        self.doc = doc
        self.index = index
        self.path = doc.section_paths[index]
        self.src = doc.text(self.path)
        self.root = doc.tree(self.path)
        self.sec = xmlspan.document_element(self.root)
        self._tables: Optional[List[Table]] = None

    @property
    def hp(self) -> str:
        p = self.doc.prefix(self.path, "http://www.hancom.co.kr/hwpml/2011/paragraph")
        return p or "hp"

    def paragraphs(self) -> List[xmlspan.Node]:
        return self.sec.findall("p")

    def tables(self) -> List[Table]:
        if self._tables is None:
            out: List[Table] = []
            for i, tbl in enumerate(self.sec.iter("tbl")):
                out.append(Table(tbl, self.index, i))
            by_node = {id(t.node): t for t in out}
            for t in out:
                tc = t.node.ancestor("tc")
                if tc is not None:
                    parent_tbl = tc.ancestor("tbl")
                    pt = by_node.get(id(parent_tbl)) if parent_tbl is not None else None
                    if pt is not None:
                        for c in pt.cells(self.src):
                            if c.tc is tc:
                                t.parent_cell = c.address
                                break
            self._tables = out
        return self._tables

    def table(self, index: int) -> Table:
        tabs = self.tables()
        if not 0 <= index < len(tabs):
            raise HwpxError(f"표 s{self.index}.t{index} 가 없습니다 (표 {len(tabs)}개)")
        return tabs[index]

    def table_of(self, node: xmlspan.Node) -> Optional[Table]:
        for t in self.tables():
            if t.node is node:
                return t
        return None

    def cell_of(self, p: xmlspan.Node) -> Optional[Cell]:
        """문단이 들어 있는 가장 가까운 표 셀."""
        tc = p.ancestor("tc")
        if tc is None:
            return None
        tbl = tc.ancestor("tbl")
        t = self.table_of(tbl) if tbl is not None else None
        if t is None:
            return None
        for c in t.cells(self.src):
            if c.tc is tc:
                return c
        return None

    def paragraph_address(self, p: xmlspan.Node) -> str:
        cell = self.cell_of(p)
        if cell is not None:
            sl = cell.sublist
            idx = sl.findall("p").index(p) if sl is not None and p in sl.children else 0
            return f"{cell.address}.p{idx}"
        top = p
        while top.parent is not None and top.parent is not self.sec:
            top = top.parent
        tops = self.paragraphs()
        ti = tops.index(top) if top in tops else 0
        if top is p:
            return f"s{self.index}.p{ti}"
        return f"s{self.index}.p{ti}+{_where(p)}"

    def iter_paragraphs(self) -> Iterator[xmlspan.Node]:
        return self.sec.iter("p")


def _where(p: xmlspan.Node) -> str:
    for a in p.ancestors():
        loc = a.local
        if loc in ("header", "footer"):
            return "머리말" if loc == "header" else "꼬리말"
        if loc in ("footNote", "endNote"):
            return "각주" if loc == "footNote" else "미주"
        if loc == "drawText":
            return "글상자"
    return "개체"


def where_label(p: xmlspan.Node) -> str:
    for a in p.ancestors():
        if a.local == "tc":
            return "표"
        if a.local in ("header", "footer", "footNote", "endNote", "drawText"):
            return _where(p)
    return "본문"


_ADDR_RE = re.compile(r"^s(\d+)(?:\.t(\d+)(?:\.r(\d+)\.c(\d+)(?:\.p(\d+))?)?|\.p(\d+))$")


def parse_address(addr: str) -> Dict[str, Optional[int]]:
    m = _ADDR_RE.match(addr.strip())
    if not m:
        raise HwpxError(f"주소 형식이 올바르지 않습니다: {addr!r} (예: s0.t1.r2.c1, s0.p3)")
    s, t, r, c, cp, p = m.groups()
    return {"section": int(s), "table": _opt(t), "row": _opt(r), "col": _opt(c),
            "cell_para": _opt(cp), "para": _opt(p)}


def _opt(v: Optional[str]) -> Optional[int]:
    return int(v) if v is not None else None
