"""양식 채우기.

입력(JSON)
{
  "values":    {"제목": "…", "기관명": "…", "성명": ["홍길동", "김철수"], "생년월일": {"value": "19900315", "format": "date:yyyy. m. d."}},
  "cells":     {"s0.t1.r2.c1": "□ 추진 배경\\n ○ …"},
  "rows":      {"s0.t2": [{"성명": "홍길동", "학년": "3"}, …]},
  "equations": {"0": "{a+b} over {2}"},
  "options":   {"require_unique": false}
}
- values 키는 누름틀 이름 → {{자리표시}} → 표 라벨 → 본문 라벨 → 체크박스·괄호 순으로 찾는다.
  문자열 값은 같은 이름의 모든 자리에, 배열 값은 문서 순서대로 하나씩 들어간다.
- 여러 줄·항목부호·`<eq>` 수식이 든 값은 양식의 예시 서식을 익혀 문단으로 쓴다 (content.py).
- 명단표(rows)는 데이터가 양식의 행보다 많으면 마지막 데이터 행을 서식째 복제해 늘리고,
  남는 빈 행은 그대로 둔다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from . import tables as table_ops
from .content import StyleBook, WriteContext, cell_splices, is_rich, range_splices, run_content
from .core import xmlspan
from .core.model import Section, parse_address
from .core.splice import Splice
from .core.text import ParaText, inline_xml
from .equation import check_script, has_eq_markup, replace_equation, resolve_equation, split_eq_markup
from .errors import HwpxError
from .forms import (CHECK_TRUE, FieldSlot, PlaceholderSlot, detect_header_row, find_matching_key,
                    normalize_label, scan_document)

PRIORITY = {"cell": 0, "row": 1, "field": 2, "placeholder": 3, "label": 4, "inline": 5, "pattern": 6}


# ── 값 서식 (kordoc formatFillValue 이식) ─────────────────────────────────
def _parse_ymd(v: str) -> Optional[Tuple[str, str, str]]:
    parts = [x for x in re.split(r"[^0-9]+", v) if x]
    if len(parts) == 3:
        yp, mp, dp = parts
        y = yp if len(yp) >= 3 else str(2000 + int(yp) if int(yp) <= 29 else 1900 + int(yp))
        m, d = mp.zfill(2), dp.zfill(2)
    else:
        dd = re.sub(r"\D", "", v)
        if len(dd) >= 8:
            y, m, d = dd[:4], dd[4:6], dd[6:8]
        elif len(dd) == 6:
            yy = int(dd[:2])
            y, m, d = str(2000 + yy if yy <= 29 else 1900 + yy), dd[2:4], dd[4:6]
        else:
            return None
    if not (1 <= int(m) <= 12 and 1 <= int(d) <= 31):
        return None
    return y, m, d


def format_value(value: str, fmt: Optional[str]) -> str:
    if not fmt:
        return value
    kind, _, style = fmt.partition(":")
    if kind == "date" or (not style and re.search(r"yyyy|yy|mm|dd", fmt)):
        p = _parse_ymd(value)
        if not p:
            return value
        y, m, d = p
        pat = style if kind == "date" else fmt
        pat = pat or "yyyy. m. d."
        out = re.sub("yyyy", y, pat, flags=re.I)
        out = re.sub("yy", y[2:], out, flags=re.I)
        out = re.sub("mm", m, out, flags=re.I)
        out = re.sub("dd", d, out, flags=re.I)
        out = re.sub(r"(?<![A-Za-z])m(?![A-Za-z])", str(int(m)), out, flags=re.I)
        out = re.sub(r"(?<![A-Za-z])d(?![A-Za-z])", str(int(d)), out, flags=re.I)
        return out
    if kind == "phone":
        dd = re.sub(r"\D", "", value)
        if len(dd) < 9:
            return value
        n = 2 if dd.startswith("02") else 3
        a, b, c = dd[:n], dd[n:-4], dd[-4:]
        return {"digits": dd, "dot": f"{a}.{b}.{c}", "space": f"{a} {b} {c}"}.get(style, f"{a}-{b}-{c}")
    if kind == "rrn":
        dd = re.sub(r"\D", "", value)
        if len(dd) != 13:
            return value
        return {"digits": dd, "front": dd[:6], "masked": f"{dd[:6]}-{dd[6]}******"}.get(style, f"{dd[:6]}-{dd[6:]}")
    if kind in ("mask",) or "#" in fmt:
        pat = style if kind == "mask" else fmt
        dd = re.sub(r"\D", "", value)
        if pat.count("#") != len(dd) or not dd:
            return value
        it = iter(dd)
        return re.sub("#", lambda _: next(it), pat)
    if kind == "digits":
        return re.sub(r"\D", "", value) or value
    if kind == "upper":
        return value.upper()
    if kind == "lower":
        return value.lower()
    if kind == "nospace":
        return re.sub(r"\s+", "", value)
    return value


class Values:
    """입력 값 모음 — 원래 키/정규화 키로 찾고, 배열 값은 순서대로 소진한다."""

    def __init__(self, raw: Dict[str, Any]):
        self.orig: Dict[str, Any] = {}
        self.norm_to_orig: Dict[str, str] = {}
        for k, v in (raw or {}).items():
            fmt = None
            if isinstance(v, dict):
                fmt = v.get("format")
                v = v.get("value", "")
            if isinstance(v, list):
                v = [format_value(str(x), fmt) for x in v]
            else:
                v = format_value("" if v is None else str(v), fmt)
            self.orig[k] = v
            self.norm_to_orig.setdefault(normalize_label(k), k)
        self._pos: Dict[str, int] = {}
        self.used: Dict[str, int] = {}

    def lookup(self, name: str, fuzzy: bool = False) -> Optional[str]:
        """자리 이름에 맞는 원래 키."""
        if name in self.orig and self.available(name):
            return name
        n = normalize_label(name)
        k = self.norm_to_orig.get(n)
        if k is not None and self.available(k):
            return k
        if fuzzy and n:
            nk = find_matching_key(n, [x for x in self.norm_to_orig if self.available(self.norm_to_orig[x])])
            if nk is not None:
                return self.norm_to_orig[nk]
        return None

    def available(self, key: str) -> bool:
        v = self.orig.get(key)
        if v is None:
            return False
        return not isinstance(v, list) or self._pos.get(key, 0) < len(v)

    def peek(self, key: str) -> Optional[str]:
        v = self.orig.get(key)
        if isinstance(v, list):
            i = self._pos.get(key, 0)
            return v[i] if i < len(v) else None
        return v

    def take(self, key: str) -> Optional[str]:
        v = self.peek(key)
        if v is None:
            return None
        if isinstance(self.orig[key], list):
            self._pos[key] = self._pos.get(key, 0) + 1
        self.used[key] = self.used.get(key, 0) + 1
        return v

    def is_list(self, key: str) -> bool:
        return isinstance(self.orig.get(key), list)

    def unused(self) -> List[str]:
        return [k for k in self.orig if k not in self.used]


@dataclass
class Edit:
    kind: str
    start: int
    end: int
    splices: List[Splice]
    info: Dict

    @property
    def priority(self) -> int:
        return PRIORITY[self.kind]


@dataclass
class FillReport:
    filled: List[Dict] = field(default_factory=list)
    skipped: List[Dict] = field(default_factory=list)
    rows_added: List[Dict] = field(default_factory=list)
    unmatched_keys: List[str] = field(default_factory=list)
    equations: List[Dict] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {"filled": self.filled, "skipped": self.skipped, "rows_added": self.rows_added,
                "unmatched_keys": self.unmatched_keys, "equations": self.equations, "notes": self.notes,
                "warnings": self.warnings,
                "summary": {"filled": len(self.filled), "skipped": len(self.skipped),
                            "rows_added": sum(r["count"] for r in self.rows_added),
                            "unmatched_keys": len(self.unmatched_keys)}}


def _preview(v: str) -> str:
    v = v.replace("\n", " ⏎ ")
    return v if len(v) <= 60 else v[:59] + "…"


def _check_values_eq(values: Dict[str, Any], cells: Dict[str, Any], report: FillReport) -> None:
    def scan(v: Any, where: str) -> None:
        if isinstance(v, dict):
            v = v.get("value", "")
        items = v if isinstance(v, list) else [v]
        for it in items:
            if isinstance(it, dict):
                for x in it.values():
                    scan(x, where)
                continue
            if isinstance(it, list):
                for x in it:
                    scan(x, where)
                continue
            s = str(it)
            if not has_eq_markup(s):
                continue
            for kind, val in split_eq_markup(s):
                if kind in ("eq", "eqblock"):
                    for f in check_script(val):
                        msg = f"{where}: 수식 `{val[:40]}` — {f.message}"
                        if f.severity == "error":
                            raise HwpxError(msg)
                        report.warnings.append(msg)
    for k, v in (values or {}).items():
        scan(v, f"values[{k}]")
    for k, v in (cells or {}).items():
        scan(v, f"cells[{k}]")


# ── 명단표 행 늘리기 ──────────────────────────────────────────────────────
def _normalize_rows(rows_in: Any) -> Tuple[Optional[int], List[Any]]:
    if isinstance(rows_in, dict):
        return rows_in.get("header_row"), list(rows_in.get("data") or rows_in.get("rows") or [])
    return None, list(rows_in or [])


def _grow_rosters(doc, rows: Dict[str, Any], report: FillReport) -> Dict[str, int]:
    """필요하면 행을 늘리고 표별 머리행(tr 번호)을 돌려준다."""
    headers: Dict[str, int] = {}
    for addr, spec in (rows or {}).items():
        a = parse_address(addr)
        if a["table"] is None:
            raise HwpxError(f"rows 키는 표 주소여야 합니다: {addr}")
        sec = Section(doc, a["section"])
        t = sec.table(a["table"])
        hdr, data = _normalize_rows(spec)
        if hdr is None:
            hdr = detect_header_row(t, sec.src)
            if hdr is None:
                hdr = 0
                report.notes.append(f"{addr}: 머리행을 찾지 못해 첫 행을 머리행으로 봄 (rows에 header_row 지정 가능)")
        headers[addr] = hdr
        n_tr = len(t.rows())
        data_trs = list(range(hdr + 1, n_tr))
        # 끝의 합계 행(합계·계·소계)은 데이터 행에서 뺀다
        while data_trs:
            last = t.row_cells(sec.src, data_trs[-1])
            first_txt = last[0].text(sec.src).strip().replace(" ", "") if last else ""
            if first_txt in ("합계", "계", "소계", "총계", "합", "총합계"):
                data_trs.pop()
            else:
                break
        need = len(data) - len(data_trs)
        if need > 0:
            template = data_trs[-1] if data_trs else hdr
            try:
                table_ops.add_rows(doc, a["section"], a["table"], template, need)
                report.rows_added.append({"table": addr, "count": need, "template_row": template})
            except HwpxError as e:
                report.warnings.append(f"{addr}: 행을 늘리지 못함 — {e} (앞 {len(data_trs)}명만 채움)")
    return headers


# ── 편집 모으기 ──────────────────────────────────────────────────────────
class _Collector:
    def __init__(self, doc, sec: Section, values: Values, report: FillReport, opts: Dict):
        self.doc = doc
        self.sec = sec
        self.src = sec.src
        self.values = values
        self.report = report
        self.opts = opts
        self.ctx = WriteContext(doc, sec.src, sec.hp)
        self.edits: List[Edit] = []

    def add(self, kind: str, splices: List[Splice], info: Dict, rng: Optional[Tuple[int, int]] = None) -> None:
        if not splices:
            return
        if rng is None:
            rng = (min(s.start for s in splices), max(s.end for s in splices))
        self.edits.append(Edit(kind, rng[0], rng[1], splices, info))

    # 셀 쓰기 (명시 셀·명단표·라벨 값 칸 공통)
    def write_cell(self, kind: str, cell, value: str, info: Dict) -> None:
        paras = cell.paragraphs()
        if not paras:
            self.report.skipped.append({**info, "reason": "셀에 문단이 없음"})
            return
        n_before = len(self.ctx.notes)
        sp = cell_splices(self.ctx, cell, value, self._table_examples(cell))
        for note in self.ctx.notes[n_before:]:
            self.report.notes.append(note)
        self.add(kind, sp, {**info, "value": _preview(value)}, (paras[0].start, paras[-1].end))

    def _table_examples(self, cell) -> List[xmlspan.Node]:
        """같은 표의 다른 셀 문단 중 항목부호로 시작하는 예시."""
        from .content import _MARKER_RE
        out = []
        for c in cell.table.cells(self.src):
            if c is cell:
                continue
            for p in c.paragraphs():
                t = ParaText(self.src, p).text
                if _MARKER_RE.match(t):
                    out.append(p)
        return out[:40]

    def fields(self, slots: List[FieldSlot]) -> None:
        spans = [(f.begin_ctrl.start, f.end_ctrl.end, f.name) for f in slots]
        for f in slots:
            if any(n == f.name and a < f.begin_ctrl.start and f.end_ctrl.end <= b for a, b, n in spans):
                # 같은 이름 누름틀 안에 또 든 누름틀(양식 작성 실수) — 바깥 것을 채우면 함께 바뀐다
                self.report.notes.append(f"{f.location}: '{f.name}' 누름틀이 같은 이름 누름틀 안에 겹쳐 있어 바깥 것만 채움")
                continue
            key = self.values.lookup(f.name)
            if key is None:
                continue
            value = self.values.take(key)
            src = self.src
            paras = [f.p_begin] if f.p_begin is f.p_end else _span_paras(f.p_begin, f.p_end)
            run = f.begin_ctrl.parent
            base_cp = int(run.get(src, "charPrIDRef") or 0) if run is not None and run.local == "run" else None
            book = StyleBook(self.doc, src, f.p_begin, paras, base_cp=base_cp)
            tag = f.begin.open_tag(src)
            new_tag = xmlspan.set_attr(tag, "dirty", "1")
            sp = range_splices(self.ctx, f.p_begin, f.a, f.p_end, f.b, value, book,
                               head_override=(f.begin.start, f.begin.open_end, new_tag))
            info = {"kind": "field", "key": key, "name": f.name, "location": f.location, "value": _preview(value)}
            self.add("field", sp, info, (f.a, f.b))

    def placeholders(self, slots: List[PlaceholderSlot]) -> None:
        src = self.src
        by_p: Dict[int, List[PlaceholderSlot]] = {}
        for ph in slots:
            by_p.setdefault(id(ph.p), []).append(ph)
        for group in by_p.values():
            p = group[0].p
            pt = ParaText(src, p)
            for ph in group:
                key = self.values.lookup(ph.key)
                if key is None:
                    continue
                value = self.values.take(key)
                info = {"kind": "placeholder", "key": key, "token": ph.token, "location": ph.location,
                        "value": _preview(value)}
                if ph.whole_paragraph and is_rich(value):
                    a = pt.raw_pos(ph.start)[0]
                    end_at = pt.raw_pos(ph.end) if ph.end < len(pt.text) else None
                    b = end_at[0] if end_at else pt.segs[-1].re
                    cell = self.sec.cell_of(p)
                    examples = cell.paragraphs() if cell is not None else [p]
                    book = StyleBook(self.doc, src, p, examples)
                    self.add("placeholder", range_splices(self.ctx, p, a, p, b, value, book), info, (a, b))
                    continue
                if "\n" in value:
                    self.report.notes.append(f"{ph.location}: {ph.token} 은 문장 중간이라 줄바꿈으로 넣음")
                xml = _inline_with_eq(self.ctx, pt, ph.start, value.replace("<eq block>", "<eq>"))
                self.add("placeholder", pt.replace(ph.start, ph.end, xml), info)

    def labels(self, slots) -> None:
        src = self.src
        seen_value_cells = set()
        for lb in slots:
            if id(lb.value_cell.tc) in seen_value_cells:
                continue
            key = self.values.lookup(lb.label, fuzzy=True)
            if key is None:
                continue
            value = self.values.peek(key)
            # 값 칸이 체크박스(□남 □여)이고 값이 선택지 중 하나면 그 칸에 체크
            vtext = lb.value_cell.text(src)
            opts = re.findall(r"□\s?([가-힣A-Za-z]+)", vtext)
            if opts and len(opts) * 2 >= len(re.findall(r"[가-힣A-Za-z]+", vtext)):
                # 선택지만 있는 칸: 고른 것에 체크 (여럿은 쉼표로), 선택지에 없는 값이면 칸을 지우지 않고 건너뜀
                norm_opts = [normalize_label(o) for o in opts]
                picks = [x for x in re.split(r"[,/·]", value or "") if x.strip()]
                if picks and all(normalize_label(x) in norm_opts for x in picks):
                    self.values.take(key)
                    for x in picks:
                        self._check_option(lb.value_cell, x, key)
                else:
                    self.report.skipped.append({"kind": "label", "key": key, "location": lb.value_cell.address,
                                                "reason": f"선택지({' '.join('□' + o for o in opts)})에 없는 값: {value}"})
                seen_value_cells.add(id(lb.value_cell.tc))
                continue
            value = self.values.take(key)
            seen_value_cells.add(id(lb.value_cell.tc))
            self.write_cell("label", lb.value_cell, value,
                            {"kind": "label", "key": key, "label": lb.label, "location": lb.value_cell.address})

    def _check_option(self, cell, value: str, key: str) -> None:
        src = self.src
        want = normalize_label(value)
        for p in cell.paragraphs():
            pt = ParaText(src, p)
            for m in re.finditer(r"□(\s?)([가-힣A-Za-z]+)", pt.text):
                if normalize_label(m.group(2)) == want:
                    self.add("label", pt.replace(m.start(), m.start() + 1, "☑"),
                             {"kind": "checkbox", "key": key, "label": m.group(2), "location": cell.address,
                              "value": "☑"})
                    return

    def inlines(self, slots) -> None:
        src = self.src
        for il in slots:
            key = None
            if il.ext_label:
                key = self.values.lookup(il.ext_label)
            if key is None:
                key = self.values.lookup(il.label, fuzzy=True)
            if key is None:
                continue
            value = self.values.take(key)
            pt = ParaText(src, il.p)
            text = pt.text
            vs, ve = il.value_start, il.value_end
            cur = text[vs:ve]
            if cur.strip("_ ") == "":
                # 빈 자리: 쌍점 뒤 공백·밑줄을 값 하나로 바꾼다 ('연락처:      ' → '연락처: 값')
                while vs > 0 and text[vs - 1] in " \t":
                    vs -= 1
                if ve < len(text) and text[ve] in " \t_":
                    stop = ve
                    while stop < len(text) and text[stop] in "_":
                        stop += 1
                    ve = stop
                ins = " " + value
                if re.match(r"[^\s:：]{1,12}[:：]", text[ve:]):
                    ins = ins + "  "  # 바로 뒤에 다음 라벨이 붙어 있으면 띄움 ('성명:____연락처:')
            else:
                ins = value
            xml = _inline_with_eq(self.ctx, pt, vs, ins)
            self.add("inline", pt.replace(vs, ve, xml),
                     {"kind": "inline", "key": key, "label": il.ext_label or il.label, "location": il.location,
                      "value": _preview(value)})

    def patterns(self, slots) -> None:
        src = self.src
        group_size: Dict[Tuple[int, str], int] = {}
        for ps in slots:
            if ps.kind == "checkbox" and ps.alt_label:
                k = (ps.p.start, ps.alt_label)
                group_size[k] = group_size.get(k, 0) + 1
        for ps in slots:
            if ps.kind == "checkbox":
                key = self.values.lookup(ps.label)
                val = (self.values.peek(key) or "").strip() if key is not None else ""
                if key is not None and val in CHECK_TRUE:
                    self.values.take(key)
                elif ps.alt_label and not self.values.is_list(self.values.lookup(ps.alt_label) or ""):
                    # 묶음 이름으로 고르기: {"성별": "남"} → '성별 □남 □여' 의 □남
                    key = self.values.lookup(ps.alt_label)
                    if key is None:
                        continue
                    gval = (self.values.peek(key) or "").strip()
                    picks = {normalize_label(x) for x in re.split(r"[,/·]", gval) if x.strip()}
                    single = group_size.get((ps.p.start, ps.alt_label)) == 1 and gval in CHECK_TRUE
                    if normalize_label(ps.label) not in picks and not single:
                        continue
                    self.values.used[key] = self.values.used.get(key, 0) + 1
                else:
                    continue
                pt = ParaText(src, ps.p)
                self.add("pattern", pt.replace(ps.start, ps.end, "☑"),
                         {"kind": "checkbox", "key": key, "label": ps.label, "location": ps.location, "value": "☑"})
            else:
                key = self.values.lookup(ps.label)
                if key is None and ps.alt_label:
                    key = self.values.lookup(ps.alt_label)
                if key is None:
                    continue
                value = self.values.take(key)
                pt = ParaText(src, ps.p)
                self.add("pattern", pt.replace(ps.start, ps.end, inline_xml(value, self.ctx.hp)),
                         {"kind": ps.kind, "key": key, "label": ps.label, "location": ps.location,
                          "value": _preview(value)})

    def explicit_cells(self, cells: Dict[str, Any]) -> None:
        for addr, value in cells.items():
            a = parse_address(addr)
            if a["section"] != self.sec.index:
                continue
            if a["table"] is not None and a["row"] is not None:
                t = self.sec.table(a["table"])
                cell = t.cell(self.src, a["row"], a["col"])
                if cell is None:
                    self.report.skipped.append({"kind": "cell", "location": addr, "reason": "셀이 없음"})
                    continue
                if isinstance(value, dict):
                    value = format_value(str(value.get("value", "")), value.get("format"))
                self.write_cell("cell", cell, str(value), {"kind": "cell", "location": addr})
            elif a["para"] is not None:
                paras = self.sec.paragraphs()
                if a["para"] >= len(paras):
                    self.report.skipped.append({"kind": "cell", "location": addr, "reason": "문단이 없음"})
                    continue
                p = paras[a["para"]]
                pt = ParaText(self.src, p)
                value = str(value)
                book = StyleBook(self.doc, self.src, p, [p])
                if not pt.segs:
                    xml = _inline_with_eq(self.ctx, pt, 0, value)
                    self.add("cell", pt.insert_new_t(xml) if not is_rich(value) else
                             range_splices(self.ctx, p, _content_start(p), p, _content_end(p), value, book),
                             {"kind": "paragraph", "location": addr, "value": _preview(value)}, (p.start, p.end))
                else:
                    a0, b0 = pt.segs[0].rs, pt.segs[-1].re
                    sp = range_splices(self.ctx, p, a0, p, b0, value, book)
                    self.add("cell", sp, {"kind": "paragraph", "location": addr, "value": _preview(value)},
                             (p.start, p.end))

    def rosters(self, rows: Dict[str, Any], headers: Dict[str, int]) -> None:
        src = self.src
        for addr, spec in rows.items():
            a = parse_address(addr)
            if a["section"] != self.sec.index:
                continue
            t = self.sec.table(a["table"])
            hdr = headers.get(addr, 0)
            _, data = _normalize_rows(spec)
            header_cells = t.row_cells(src, hdr)
            cols = [(c.text(src).strip(), c.col, c.colspan) for c in header_cells]
            n_tr = len(t.rows())
            for i, row_val in enumerate(data):
                tr = hdr + 1 + i
                if tr >= n_tr:
                    self.report.skipped.append({"kind": "row", "location": addr, "reason": f"{i + 1}번째 행 자리가 없음"})
                    continue
                row_cells = t.row_cells(src, tr)
                if not row_cells:
                    continue
                r = row_cells[0].row
                for ci, (label, col, span) in enumerate(cols):
                    if isinstance(row_val, dict):
                        norm = {normalize_label(k): k for k in row_val}
                        nk = find_matching_key(normalize_label(label), norm.keys()) if label else None
                        if nk is None:
                            continue
                        v = row_val[norm[nk]]
                    elif isinstance(row_val, (list, tuple)):
                        if ci >= len(row_val):
                            continue
                        v = row_val[ci]
                    else:
                        continue
                    if v is None:
                        continue
                    cell = t.cell(src, r, col)
                    if cell is None or cell.row != r:
                        continue
                    self.write_cell("row", cell, str(v), {"kind": "row", "location": cell.address, "column": label})

    # ── 확정 ──
    def resolve(self) -> List[Splice]:
        accepted: List[Edit] = []
        for e in sorted(self.edits, key=lambda x: (x.priority, x.start)):
            clash = next((a for a in accepted if _overlaps(a, e)), None)
            if clash is not None:
                self.report.skipped.append({**e.info, "reason": f"{clash.info.get('location')}의 {clash.kind} 채우기와 겹침"})
                continue
            accepted.append(e)
        out: List[Splice] = []
        for e in sorted(accepted, key=lambda x: x.start):
            self.report.filled.append(e.info)
            out.extend(e.splices)
        return out


def _overlaps(x: Edit, y: Edit) -> bool:
    """두 편집이 같은 원문을 건드리는지. 셀·문단 전체 쓰기는 선언한 범위로, 나머지는 교체 조각으로 본다."""
    if not (x.end <= y.start or y.end <= x.start):
        if x.kind in ("cell", "row", "label") or y.kind in ("cell", "row", "label"):
            return True
    for s1 in x.splices:
        for s2 in y.splices:
            if s1.start < s2.end and s2.start < s1.end:
                return True
            if s1.start == s2.start and (s1.end > s1.start or s2.end > s2.start):
                return True
    return False


def _span_paras(pa: xmlspan.Node, pb: xmlspan.Node) -> List[xmlspan.Node]:
    sib = pa.parent.findall("p") if pa.parent is not None else [pa]
    i0, i1 = sib.index(pa), sib.index(pb)
    return sib[i0:i1 + 1]


def _content_start(p: xmlspan.Node) -> int:
    runs = p.findall("run")
    return runs[0].start if runs else p.open_end


def _content_end(p: xmlspan.Node) -> int:
    runs = p.findall("run")
    return runs[-1].end if runs else p.open_end


def _inline_with_eq(ctx: WriteContext, pt: ParaText, at: int, value: str) -> str:
    """hp:t 안에 들어갈 인라인 XML. `<eq>`는 hp:t를 잠시 닫고 수식을 끼운다."""
    if "<eq" not in value:
        return inline_xml(value, ctx.hp)
    run = pt.run_at(at)
    cp = int(run.get(pt.src, "charPrIDRef") or 0) if run is not None else 0
    hp = ctx.hp
    out = []
    for kind, val in split_eq_markup(value):
        if kind == "text":
            out.append(inline_xml(val, hp))
        else:
            inner = run_content(ctx, f"<eq>{val}</eq>", cp)
            inner = inner.replace(f"<{hp}:t/>", "")
            out.append(f"</{hp}:t>{inner}<{hp}:t>")
    return "".join(out)


# ── 진입점 ────────────────────────────────────────────────────────────────
def fill_document(doc, data: Dict[str, Any]) -> FillReport:
    report = FillReport()
    values_in = data.get("values") or {}
    cells_in = data.get("cells") or {}
    rows_in = data.get("rows") or {}
    eq_in = data.get("equations") or {}
    opts = data.get("options") or {}
    _check_values_eq(values_in, cells_in, report)
    for k in rows_in:
        _check_values_eq({}, {f"{k}[{i}]": v for i, v in enumerate(_normalize_rows(rows_in[k])[1])}, report)

    headers = _grow_rosters(doc, rows_in, report)
    values = Values(values_in)
    for sec, scan in scan_document(doc):
        col = _Collector(doc, sec, values, report, opts)
        col.explicit_cells(cells_in)
        col.rosters(rows_in, headers)
        col.fields(scan.fields)
        col.placeholders(scan.placeholders)
        col.labels(scan.labels)
        col.inlines(scan.inlines)
        col.patterns(scan.patterns)
        splices = col.resolve()
        doc.apply(sec.path, splices)
    if opts.get("require_unique"):
        counts: Dict[str, int] = {}
        for f in report.filled:
            if f.get("kind") in ("label", "inline", "pattern") and f.get("key") and not values.is_list(f["key"]):
                counts[f["key"]] = counts.get(f["key"], 0) + 1
        dup = [k for k, n in counts.items() if n > 1]
        if dup:
            report.warnings.append("여러 곳에 들어간 키(require_unique): " + ", ".join(dup))
    for idx, script in eq_in.items():
        try:
            res = replace_equation(doc, resolve_equation(doc, idx), str(script))
            report.equations.append(res)
        except HwpxError as e:
            report.warnings.append(f"수식 {idx}: {e}")
    report.unmatched_keys = values.unused()
    for k in list(values.orig):
        if values.is_list(k) and values.available(k):
            report.warnings.append(f"'{k}' 배열 값이 남았습니다 (자리보다 값이 많음)")
    return report
