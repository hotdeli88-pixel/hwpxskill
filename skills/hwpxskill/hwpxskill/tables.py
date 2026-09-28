"""표 행 추가 — 기존 데이터 행의 서식(테두리·글꼴·높이)을 그대로 복제한다.

kordoc roundtrip/table-rows.ts의 안전 조건을 따른다: 복제할 행에 세로 병합·중첩 표·누름틀이
있거나, 위 행의 세로 병합이 그 행에 걸쳐 있으면 행을 늘리지 않는다.
"""
from __future__ import annotations

from typing import List

from .core import xmlspan
from .core.model import Section
from .core.splice import Splice, apply_splices
from .core.text import ParaText
from .errors import HwpxError

_BLOCKING = frozenset({"tbl", "pic", "equation", "ole", "container", "rect", "ellipse", "chart",
                       "fieldBegin", "fieldEnd"})


def _clear_tr(xml: str, new_row: int) -> str:
    """tr 조각을 복제용으로: 셀마다 첫 문단만 남기고 글자를 비우며 행 주소를 바꾼다."""
    root = xmlspan.parse(xml)
    tr = xmlspan.document_element(root)
    sp: List[Splice] = []
    for tc in tr.findall("tc"):
        addr = tc.find("cellAddr")
        if addr is not None:
            sp.append(Splice(addr.start, addr.open_end, xmlspan.set_attr(addr.open_tag(xml), "rowAddr", str(new_row))))
        sl = tc.find("subList")
        if sl is None:
            continue
        paras = sl.findall("p")
        if not paras:
            continue
        first = paras[0]
        pt = ParaText(xml, first)
        sp.extend(pt.set_text(""))
        for p in paras[1:]:
            sp.append(Splice(p.start, p.end, ""))
        for ls in first.findall("linesegarray"):
            sp.append(Splice(ls.start, ls.end, ""))
    return apply_splices(xml, sp)


def add_rows(doc, section: int, table: int, template_tr: int, count: int) -> List[int]:
    """template_tr 행 뒤에 같은 서식의 빈 행 count개를 넣는다. 새 tr 번호 목록을 돌려준다."""
    if count <= 0:
        return []
    sec = Section(doc, section)
    src = sec.src
    t = sec.table(table)
    trs = t.rows()
    if not 0 <= template_tr < len(trs):
        raise HwpxError(f"{t.id}: 행 {template_tr} 이 없습니다")
    tpl = trs[template_tr]
    tpl_cells = t.row_cells(src, template_tr)
    if not tpl_cells:
        raise HwpxError(f"{t.id}: 복제할 행에 셀이 없습니다")
    if any(c.rowspan > 1 for c in tpl_cells):
        raise HwpxError(f"{t.id}: 복제할 행에 세로 병합 셀이 있어 행을 늘릴 수 없습니다")
    tpl_row = min(c.row for c in tpl_cells)
    for c in t.cells(src):
        if c.tr_index != template_tr and c.row < tpl_row < c.row + c.rowspan:
            raise HwpxError(f"{t.id}: 위 행의 세로 병합이 복제할 행에 걸쳐 있어 행을 늘릴 수 없습니다")
        if c.tr_index != template_tr and c.row <= tpl_row < c.row + c.rowspan - 1:
            raise HwpxError(f"{t.id}: 세로 병합이 삽입 위치를 가로질러 행을 늘릴 수 없습니다")
    for tc in tpl.findall("tc"):
        for n in tc.iter():
            if n.local in _BLOCKING:
                raise HwpxError(f"{t.id}: 복제할 행에 표·그림·누름틀 같은 개체가 있어 행을 늘릴 수 없습니다")
    tpl_xml = tpl.outer(src)
    new_xml = "".join(_clear_tr(tpl_xml, tpl_row + k + 1) for k in range(count))
    sp: List[Splice] = [Splice(tpl.end, tpl.end, new_xml)]
    for c in t.cells(src):
        if c.tr_index > template_tr:
            addr = c.tc.find("cellAddr")
            if addr is not None:
                row = int(addr.get(src, "rowAddr") or 0)
                sp.append(Splice(addr.start, addr.open_end,
                                 xmlspan.set_attr(addr.open_tag(src), "rowAddr", str(row + count))))
    tag = t.node.open_tag(src)
    rc = t.node.get(src, "rowCnt")
    if rc is not None:
        tag = xmlspan.set_attr(tag, "rowCnt", str(int(rc) + count))
        sp.append(Splice(t.node.start, t.node.open_end, tag))
    sz = t.node.find("sz")
    row_h = max((c.height for c in tpl_cells), default=0)
    if sz is not None and row_h:
        h = int(sz.get(src, "height") or 0)
        sp.append(Splice(sz.start, sz.open_end, xmlspan.set_attr(sz.open_tag(src), "height", str(h + row_h * count))))
    doc.apply(sec.path, sp)
    return list(range(template_tr + 1, template_tr + 1 + count))
