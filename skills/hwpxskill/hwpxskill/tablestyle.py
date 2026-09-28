"""표 스타일 복제 — 원본 표(같은 문서 또는 다른 문서)의 스타일만 대상 표에 입힌다.

역할 기준으로 맞춘다: 머리행 · 라벨 열(첫 열) · 본문 · 합계행, 그리고 선은 바깥 테두리 ·
안쪽 가로/세로선 · 머리행 아래선 · 라벨 열 오른쪽 선 · 합계행 위선. 행·열 수가 달라도 적용된다.
옮기는 것: 테두리(종류·굵기·색), 셀 배경, 글자 모양(글꼴·크기·색·굵기), 문단 정렬·줄 간격,
세로 정렬, 셀 여백, 열 너비 비율(열 수가 같을 때). 대상 표의 글 내용은 바꾸지 않는다.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from .core import xmlspan
from .core.model import Cell, Section, Table, parse_address
from .core.splice import Splice
from .core.text import ParaText
from .errors import HwpxError
from .forms import detect_header_row, is_label_cell

Line = Tuple[str, str, str]  # (type, width, color)
_NONE: Line = ("NONE", "0.1 mm", "#000000")
_TOTAL_WORDS = {"합계", "계", "소계", "총계", "합", "총합계", "누계"}


@dataclass
class RoleStyle:
    fill_xml: Optional[str] = None
    charpr: Optional[int] = None
    align: Optional[str] = None
    line_spacing: Optional[int] = None
    valign: Optional[str] = None
    margin: Optional[Dict[str, str]] = None
    has_margin: Optional[str] = None


@dataclass
class TableStyle:
    doc: object
    roles: Dict[str, RoleStyle] = field(default_factory=dict)
    lines: Dict[str, Line] = field(default_factory=dict)
    widths: List[int] = field(default_factory=list)
    has_header: bool = False
    has_label: bool = False
    has_total: bool = False
    tbl_border_fill: Optional[int] = None
    cell_spacing: Optional[str] = None
    in_margin: Optional[Dict[str, str]] = None
    repeat_header: Optional[str] = None


def _is_total(text: str) -> bool:
    return text.strip().replace(" ", "") in _TOTAL_WORDS


def _cell_signature(doc, src: str, c: Cell) -> Tuple:
    bf = doc.header.borderfill(c.border_fill(src)) if doc.header.has("borderFill", c.border_fill(src)) else {}
    runs = [r for p in c.paragraphs() for r in p.findall("run")]
    cp = runs[0].get(src, "charPrIDRef") if runs else None
    bold = doc.header.charpr(int(cp))["bold"] if cp is not None and doc.header.has("charPr", int(cp)) else None
    return (bf.get("face"), bold)


def _header_rows(t: Table, src: str) -> List[int]:
    rows = sorted({c.tr_index for c in t.cells(src) if c.tc.get(src, "header") == "1"})
    if rows and rows[0] == 0:
        out = []
        for r in rows:
            if r == len(out):
                out.append(r)
        return out
    h = detect_header_row(t, src)
    return list(range(h + 1)) if h is not None else []


def _dominant_charpr(src: str, c: Cell) -> Optional[int]:
    weight: Counter = Counter()
    for p in c.paragraphs():
        pt = ParaText(src, p)
        for seg in pt.segs:
            cp = seg.run.get(src, "charPrIDRef")
            if cp is not None:
                weight[int(cp)] += len(seg.text)
        if not pt.segs:
            for r in p.findall("run"):
                cp = r.get(src, "charPrIDRef")
                if cp is not None:
                    weight[int(cp)] += 0
    if weight:
        return weight.most_common(1)[0][0]
    for p in c.paragraphs():
        for r in p.findall("run"):
            cp = r.get(src, "charPrIDRef")
            if cp is not None:
                return int(cp)
    return None


def _role_style(doc, src: str, cells: Sequence[Cell]) -> RoleStyle:
    if not cells:
        return RoleStyle()
    hs = doc.header
    fills: Counter = Counter()
    cps: Counter = Counter()
    aligns: Counter = Counter()
    spacings: Counter = Counter()
    valigns: Counter = Counter()
    for c in cells:
        bid = c.border_fill(src)
        if hs.has("borderFill", bid):
            fills[hs.borderfill(bid).get("fill_xml")] += 1
        cp = _dominant_charpr(src, c)
        if cp is not None:
            cps[cp] += 1
        for p in c.paragraphs()[:1]:
            ppr = int(p.get(src, "paraPrIDRef") or 0)
            if hs.has("paraPr", ppr):
                info = hs.parapr(ppr)
                aligns[info["align"]] += 1
                if info["lineSpacing"]["type"] == "PERCENT":
                    spacings[info["lineSpacing"]["value"]] += 1
        sl = c.sublist
        if sl is not None:
            valigns[sl.get(src, "vertAlign") or "CENTER"] += 1
    rep = cells[len(cells) // 2]
    cm = rep.tc.find("cellMargin")
    margin = {k: cm.get(src, k) for k in ("left", "right", "top", "bottom")} if cm is not None else None
    return RoleStyle(
        fill_xml=fills.most_common(1)[0][0] if fills else None,
        charpr=cps.most_common(1)[0][0] if cps else None,
        align=aligns.most_common(1)[0][0] if aligns else None,
        line_spacing=spacings.most_common(1)[0][0] if spacings else None,
        valign=valigns.most_common(1)[0][0] if valigns else None,
        margin=margin,
        has_margin=rep.tc.get(src, "hasMargin"),
    )


def _side(doc, src: str, c: Optional[Cell], side: str) -> Optional[Line]:
    if c is None:
        return None
    bid = c.border_fill(src)
    if not doc.header.has("borderFill", bid):
        return None
    return doc.header.borderfill(bid)["sides"].get(side)


def extract_style(doc, t: Table) -> TableStyle:
    src = Section(doc, t.section).src
    cells = t.cells(src)
    if not cells:
        raise HwpxError(f"{t.id}: 셀이 없는 표입니다")
    n_rows = max(c.row + c.rowspan for c in cells)
    n_cols = max(c.col + c.colspan for c in cells)
    header_trs = _header_rows(t, src)
    header_rows = {c.row for c in cells if c.tr_index in header_trs}
    last_row_cells = [c for c in cells if c.row + c.rowspan == n_rows]
    first_last = sorted(last_row_cells, key=lambda c: c.col)
    total_row = n_rows - 1 if first_last and _is_total(first_last[0].text(src)) and n_rows > 1 else None
    body = [c for c in cells if c.row not in header_rows and c.row != total_row]
    col0 = [c for c in body if c.col == 0]
    rest = [c for c in body if c.col > 0]
    has_label = False
    if n_cols >= 2 and col0 and rest:
        s0 = Counter(_cell_signature(doc, src, c) for c in col0).most_common(1)[0][0]
        s1 = Counter(_cell_signature(doc, src, c) for c in rest).most_common(1)[0][0]
        has_label = s0 != s1 or all(is_label_cell(c.text(src)) for c in col0 if c.text(src).strip())
    st = TableStyle(doc, has_header=bool(header_rows), has_label=has_label, has_total=total_row is not None)
    st.roles["header"] = _role_style(doc, src, [c for c in cells if c.row in header_rows])
    st.roles["label"] = _role_style(doc, src, col0 if has_label else [])
    st.roles["body"] = _role_style(doc, src, rest if has_label else body)
    st.roles["total"] = _role_style(doc, src, [c for c in cells if total_row is not None and c.row == total_row])

    def pick(pred) -> Optional[Cell]:
        cand = [c for c in cells if pred(c)]
        return cand[len(cand) // 2] if cand else None

    body_rows = [r for r in range(n_rows) if r not in header_rows and r != total_row]
    first_body = min(body_rows) if body_rows else 0
    lines = {
        "outer_top": _side(doc, src, pick(lambda c: c.row == 0), "topBorder"),
        "outer_bottom": _side(doc, src, pick(lambda c: c.row + c.rowspan == n_rows), "bottomBorder"),
        "outer_left": _side(doc, src, pick(lambda c: c.col == 0 and c.row in body_rows) or pick(lambda c: c.col == 0), "leftBorder"),
        "outer_right": _side(doc, src, pick(lambda c: c.col + c.colspan == n_cols and c.row in body_rows)
                             or pick(lambda c: c.col + c.colspan == n_cols), "rightBorder"),
        "inner_h": _side(doc, src, pick(lambda c: c.row in body_rows and c.row + c.rowspan < n_rows
                                         and c.row + c.rowspan != total_row), "bottomBorder"),
        "inner_v": _side(doc, src, pick(lambda c: c.row in body_rows and 0 < c.col + c.colspan < n_cols
                                         and not (has_label and c.col == 0)), "rightBorder"),
        "header_bottom": _side(doc, src, pick(lambda c: c.row in header_rows and c.row + c.rowspan == first_body),
                               "bottomBorder"),
        "header_inner_v": _side(doc, src, pick(lambda c: c.row in header_rows and c.col + c.colspan < n_cols),
                                "rightBorder"),
        "label_right": _side(doc, src, pick(lambda c: c.col == 0 and c.row in body_rows), "rightBorder"),
        "total_top": _side(doc, src, pick(lambda c: total_row is not None and c.row == total_row), "topBorder"),
    }
    fallback = lines["inner_h"] or lines["inner_v"] or lines["outer_top"] or ("SOLID", "0.12 mm", "#000000")
    st.lines = {k: (v or (lines["inner_v"] if k in ("header_inner_v", "label_right") else None)
                    or (lines["inner_h"] if k in ("header_bottom", "total_top") else None) or fallback)
                for k, v in lines.items()}
    colw = [0] * n_cols
    for c in cells:
        if c.colspan == 1 and c.width and not colw[c.col]:
            colw[c.col] = c.width
    st.widths = colw if all(colw) else []
    st.tbl_border_fill = int(t.node.get(src, "borderFillIDRef") or 0) or None
    st.cell_spacing = t.node.get(src, "cellSpacing")
    im = t.node.find("inMargin")
    st.in_margin = {k: im.get(src, k) for k in ("left", "right", "top", "bottom")} if im is not None else None
    st.repeat_header = t.node.get(src, "repeatHeader")
    return st


# ── 적용 ──────────────────────────────────────────────────────────────────
def _bf_xml(prefix_h: str, prefix_c: str, sides: Dict[str, Line], fill_xml: Optional[str]) -> str:
    parts = [f'<{prefix_h}:borderFill id="0" threeD="0" shadow="0" centerLine="NONE" breakCellSeparateLine="0">',
             f'<{prefix_h}:slash type="NONE" Crooked="0" isCounter="0"/>',
             f'<{prefix_h}:backSlash type="NONE" Crooked="0" isCounter="0"/>']
    for side in ("leftBorder", "rightBorder", "topBorder", "bottomBorder"):
        typ, width, color = sides.get(side, _NONE)
        parts.append(f'<{prefix_h}:{side} type="{typ}" width="{width}" color="{color}"/>')
    parts.append(f'<{prefix_h}:diagonal type="SOLID" width="0.1 mm" color="#000000"/>')
    if fill_xml:
        parts.append(_retag(fill_xml, prefix_c))
    parts.append(f"</{prefix_h}:borderFill>")
    return "".join(parts)


def _retag(xml: str, prefix_c: str) -> str:
    import re
    return re.sub(r"<(/?)\w+:(fillBrush|winBrush|gradation|color|imgBrush|img)\b", rf"<\1{prefix_c}:\2", xml)


class _Applier:
    def __init__(self, doc, style: TableStyle, same_doc: bool):
        self.doc = doc
        self.st = style
        self.same = same_doc
        self._cp_cache: Dict[Tuple[int, Tuple], int] = {}
        self._imported_cp: Dict[int, int] = {}

    def role_charpr(self, role: RoleStyle) -> Optional[int]:
        if role.charpr is None:
            return None
        if self.same:
            return role.charpr
        if role.charpr not in self._imported_cp:
            self._imported_cp[role.charpr] = self.doc.header.import_charpr(self.st.doc.header, role.charpr)
        return self._imported_cp[role.charpr]

    def run_charpr(self, role: RoleStyle, run_cp: int, dominant: Optional[int]) -> Optional[int]:
        base = self.role_charpr(role)
        if base is None:
            return None
        if dominant is None or run_cp == dominant:
            return base
        hs = self.doc.header
        info = hs.charpr(run_cp)
        key = (base, (info["bold"], info["italic"], info["underline"]))
        if key not in self._cp_cache:
            b = hs.charpr(base)
            same = (b["bold"], b["italic"], b["underline"]) == key[1]
            self._cp_cache[key] = base if same else hs.derive_charpr(
                base, bold=info["bold"], italic=info["italic"], underline=info["underline"])
        return self._cp_cache[key]


def apply_table_style(doc, targets: Sequence[str], source: str, source_doc=None, widths: bool = True) -> Dict:
    src_doc = source_doc or doc
    sa = parse_address(source)
    if sa["table"] is None:
        raise HwpxError(f"원본 표 주소가 아닙니다: {source} (예: s0.t0)")
    style = extract_style(src_doc, Section(src_doc, sa["section"]).table(sa["table"]))
    same = src_doc is doc
    ap = _Applier(doc, style, same)
    log = [f"원본 {source}: 머리행 {'있음' if style.has_header else '없음'}, 라벨 열 {'있음' if style.has_label else '없음'}, "
           f"합계행 {'있음' if style.has_total else '없음'}"]
    tbf = None
    if style.tbl_border_fill:
        tbf = style.tbl_border_fill if same else doc.header.import_borderfill(src_doc.header, style.tbl_border_fill)
    for addr in targets:
        a = parse_address(addr)
        if a["table"] is None:
            raise HwpxError(f"대상 표 주소가 아닙니다: {addr}")
        sec = Section(doc, a["section"])
        t = sec.table(a["table"])
        n = _apply_one(doc, sec, t, ap, tbf, widths)
        log.append(f"{addr}: 셀 {n}개에 적용")
    return {"source": source, "targets": list(targets), "log": log}


def _apply_one(doc, sec: Section, t: Table, ap: _Applier, tbf: Optional[int], widths: bool) -> int:
    st = ap.st
    src = sec.src
    hs = doc.header
    ph = next((c.prefix for c in hs.doc.tree(hs.path).iter("borderFill")), "hh") or "hh"
    pc = sec.doc.prefix(hs.path, "http://www.hancom.co.kr/hwpml/2011/core") or "hc"
    cells = t.cells(src)
    n_rows = max(c.row + c.rowspan for c in cells)
    n_cols = max(c.col + c.colspan for c in cells)
    header_rows: set = set()
    if st.has_header:
        trs = _header_rows(t, src)
        if not trs:
            row0 = [c for c in cells if c.row == 0]
            col0 = [c.text(src) for c in cells if c.col == 0 and c.text(src).strip()]
            label_value = n_cols == 2 and col0 and all(is_label_cell(x) for x in col0)
            if (row0 and n_rows > 1 and not label_value
                    and all(is_label_cell(c.text(src)) for c in row0 if c.text(src).strip())):
                trs = [row0[0].tr_index]
        header_rows = {c.row for c in cells if c.tr_index in trs}
    last = sorted([c for c in cells if c.row + c.rowspan == n_rows], key=lambda c: c.col)
    total_row = n_rows - 1 if st.has_total and last and _is_total(last[0].text(src)) and n_rows > 1 else None
    label_col = st.has_label and n_cols >= 2
    body_rows = [r for r in range(n_rows) if r not in header_rows and r != total_row]
    first_body = min(body_rows) if body_rows else n_rows
    L = st.lines

    new_w: Optional[List[int]] = None
    if widths and st.widths and len(st.widths) == n_cols:
        total_w = int(t.node.find("sz").get(src, "width") or 0) if t.node.find("sz") is not None else 0
        if not total_w:
            total_w = sum(c.width for c in cells if c.row == 0)
        s = sum(st.widths)
        new_w = [int(round(w * total_w / s)) for w in st.widths]
        new_w[-1] += total_w - sum(new_w)

    splices: List[Splice] = []
    count = 0
    for c in cells:
        role_name = ("header" if c.row in header_rows else "total" if c.row == total_row
                     else "label" if label_col and c.col == 0 else "body")
        role = st.roles.get(role_name) or RoleStyle()
        if not any([role.fill_xml, role.charpr is not None, role.align]) and role_name in ("label", "total"):
            role = st.roles["body"]
        top = (L["outer_top"] if c.row == 0 else L["header_bottom"] if c.row == first_body and header_rows
               else L["total_top"] if c.row == total_row else L["inner_h"])
        end_r = c.row + c.rowspan
        bottom = (L["outer_bottom"] if end_r == n_rows else L["header_bottom"] if end_r == first_body and header_rows
                  else L["total_top"] if total_row is not None and end_r == total_row else L["inner_h"])
        is_head = c.row in header_rows
        inner_v = L["header_inner_v"] if is_head else L["inner_v"]
        left = (L["outer_left"] if c.col == 0 else L["label_right"] if label_col and c.col == 1 and not is_head
                else inner_v)
        end_c = c.col + c.colspan
        right = (L["outer_right"] if end_c == n_cols else L["label_right"] if label_col and end_c == 1 and not is_head
                 else inner_v)
        bf = hs.add("borderFill", _bf_xml(ph, pc, {"leftBorder": left, "rightBorder": right, "topBorder": top,
                                                    "bottomBorder": bottom}, role.fill_xml))
        tag = c.tc.open_tag(src)
        tag = xmlspan.set_attr(tag, "borderFillIDRef", str(bf))
        if st.has_header:
            tag = xmlspan.set_attr(tag, "header", "1" if is_head else "0")
        if role.has_margin is not None:
            tag = xmlspan.set_attr(tag, "hasMargin", role.has_margin)
        splices.append(Splice(c.tc.start, c.tc.open_end, tag))
        sl = c.sublist
        if sl is not None and role.valign:
            splices.append(Splice(sl.start, sl.open_end, xmlspan.set_attr(sl.open_tag(src), "vertAlign", role.valign)))
        cm = c.tc.find("cellMargin")
        if cm is not None and role.margin:
            mt = cm.open_tag(src)
            for k, v in role.margin.items():
                if v is not None:
                    mt = xmlspan.set_attr(mt, k, v)
            splices.append(Splice(cm.start, cm.open_end, mt))
        if new_w is not None:
            sz = c.tc.find("cellSz")
            if sz is not None:
                w = sum(new_w[c.col:c.col + c.colspan])
                splices.append(Splice(sz.start, sz.open_end, xmlspan.set_attr(sz.open_tag(src), "width", str(w))))
        dominant = _dominant_charpr(src, c)
        for p in c.paragraphs():
            ppr = int(p.get(src, "paraPrIDRef") or 0)
            if role.align or role.line_spacing:
                new_ppr = hs.derive_parapr(ppr, align=role.align, line_spacing=role.line_spacing)
                if new_ppr != ppr:
                    splices.append(Splice(p.start, p.open_end,
                                          xmlspan.set_attr(p.open_tag(src), "paraPrIDRef", str(new_ppr))))
            for r in p.findall("run"):
                cp = int(r.get(src, "charPrIDRef") or 0)
                ncp = ap.run_charpr(role, cp, dominant)
                if ncp is not None and ncp != cp:
                    splices.append(Splice(r.start, r.open_end,
                                          xmlspan.set_attr(r.open_tag(src), "charPrIDRef", str(ncp))))
        count += 1
    ttag = t.node.open_tag(src)
    if tbf is not None:
        ttag = xmlspan.set_attr(ttag, "borderFillIDRef", str(tbf))
    if st.cell_spacing is not None:
        ttag = xmlspan.set_attr(ttag, "cellSpacing", st.cell_spacing)
    if st.repeat_header is not None and header_rows:
        ttag = xmlspan.set_attr(ttag, "repeatHeader", st.repeat_header)
    splices.append(Splice(t.node.start, t.node.open_end, ttag))
    im = t.node.find("inMargin")
    if im is not None and st.in_margin:
        mt = im.open_tag(src)
        for k, v in st.in_margin.items():
            if v is not None:
                mt = xmlspan.set_attr(mt, k, v)
        splices.append(Splice(im.start, im.open_end, mt))
    doc.apply(sec.path, splices)
    return count
