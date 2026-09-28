"""양식에서 채울 자리 찾기.

라벨 인식·매칭 규칙은 kordoc(MIT) form/recognize.ts·match.ts를 옮겨 왔다.
- 누름틀: `hp:fieldBegin type="CLICK_HERE"` ~ 짝 `hp:fieldEnd` (여러 문단에 걸칠 수 있음)
- 자리표시: `{{키}}`, `${키}` (서식 때문에 여러 run으로 쪼개져 있어도 찾음)
- 표 라벨 칸: 라벨 셀 → 같은 행 오른쪽 셀
- 명단표: 첫 행이 모두 라벨인 표의 데이터 행
- 본문 라벨: `신청인:  ` 같은 문단 속 라벨 (표 밖)
- 칸 속 패턴: `□남`(체크), `일반(  )통`(괄호 빈칸), `(한자：   )`
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Set, Tuple

from .core import xmlspan
from .core.model import Cell, Section, Table
from .core.text import ParaText

LABEL_KEYWORDS = {
    "성명", "이름", "주소", "전화", "전화번호", "휴대폰", "핸드폰", "연락처",
    "생년월일", "주민등록번호", "소속", "직위", "직급", "부서",
    "이메일", "팩스", "학교", "학년", "반", "번호",
    "신청인", "대표자", "담당자", "작성자", "확인자", "승인자",
    "일시", "날짜", "기간", "장소", "목적", "사유", "비고",
    "금액", "수량", "단가", "합계", "계", "소계",
    "등록기준지", "본적", "위임인", "청구사유", "소명자료",
}
_ENGLISH_LABEL_WORDS = {
    "name", "date", "address", "tel", "phone", "mobile", "fax", "email", "e-mail",
    "dept", "department", "division", "title", "position", "grade", "rank",
    "birth", "nationality", "sex", "gender", "signature", "sign", "seal",
    "remarks", "note", "period", "place", "purpose", "reason", "amount", "total",
    "sum", "qty", "quantity", "unit", "no", "id", "passport",
}
_ENGLISH_STOPWORDS = {"of", "the", "and", "or", "in"}
_NUMERIC_VALUE_RE = re.compile(
    r"^제?\d+(?:[.,]\d+)*[십백천만억조]*(?:원|명|건|개|회|부|매|장|점|호|번|년|월|일|시|분|초|개월|주년|차례|퍼센트)?$")
_SENTENCE_ENDING_RE = re.compile(
    r"(?:입니다|합니다|습니다|하세요|십시오|시오|바랍니다|바람|할 것|할것|하며|하고|한다|된다|됨|음|임)$")
_FOOTNOTE_TAIL_RE = re.compile(r"[¹²³⁴⁵⁶⁷⁸⁹⁰*※]+$")
PLACEHOLDER_RE = re.compile(r"\{\{\s*([^{}\n]{1,60}?)\s*\}\}|\$\{\s*([^{}\n]{1,60}?)\s*\}")
_INLINE_LABEL_RE = re.compile(r"((?:[가-힣A-Za-z]{1,10} )?)([가-힣A-Za-z]{2,10})\s*[:：]")
CHECK_TRUE = {"☑", "✓", "✔", "v", "V", "true", "True", "1", "yes", "o", "O", "예", "Y", "y", "■", "●"}


def normalize_label(label: str) -> str:
    return re.sub(r"[:：\s()（）·]", "", label.strip())


def is_label_cell(text: str) -> bool:
    trimmed = _FOOTNOTE_TAIL_RE.sub("", text.strip()).strip()
    if not trimmed or len(trimmed) > 30:
        return False
    for kw in LABEL_KEYWORDS:
        if kw in trimmed:
            return True
    compact = re.sub(r"\s", "", trimmed)
    if (re.fullmatch(r"[가-힣0-9()（）·:：\-]+", compact) and 2 <= len(compact) <= 12
            and len(re.findall(r"[가-힣]", compact)) >= 2
            and (len(compact) <= 8 or len(trimmed.split()) <= 2)
            and not _NUMERIC_VALUE_RE.match(compact)
            and not _SENTENCE_ENDING_RE.search(trimmed)
            and not re.match(r"^[(（]주[)）]|^주식회사", compact)):
        return True
    if re.fullmatch(r"[가-힣A-Za-z\s]+[:：]", trimmed):
        return True
    if re.fullmatch(r"[A-Za-z][A-Za-z\s./&-]*", trimmed) and len(trimmed) <= 20:
        words = [w for w in re.split(r"[\s/&]+", trimmed.lower()) if w and w not in _ENGLISH_STOPWORDS]
        if 1 <= len(words) <= 3 and all(w.rstrip(".") in _ENGLISH_LABEL_WORDS for w in words):
            return True
    return False


def is_keyword_label(text: str) -> bool:
    trimmed = _FOOTNOTE_TAIL_RE.sub("", text.strip()).strip()
    if not trimmed or len(trimmed) > 15:
        return False
    return any(kw in trimmed for kw in LABEL_KEYWORDS)


def find_matching_key(cell_label: str, keys: Iterable[str]) -> Optional[str]:
    """정규화된 셀 라벨에 맞는 입력 키 (정확 일치 → 접두 일치, 긴 것 우선)."""
    keys = list(keys)
    if cell_label in keys:
        return cell_label
    best, best_len = None, 0
    for key in keys:
        if not key:
            continue
        if cell_label.startswith(key):
            if len(key) >= len(cell_label) * 0.6 and len(key) > best_len:
                best, best_len = key, len(key)
        elif key.startswith(cell_label):
            if len(cell_label) >= len(key) * 0.75 and len(cell_label) > best_len:
                best, best_len = key, len(cell_label)
    return best


# ── 자리 ────────────────────────────────────────────────────────────────
@dataclass
class FieldSlot:
    name: str
    section: int
    begin: xmlspan.Node
    begin_ctrl: xmlspan.Node
    end_ctrl: xmlspan.Node
    p_begin: xmlspan.Node
    p_end: xmlspan.Node
    guide: str
    current: str
    location: str
    kind: str = "CLICK_HERE"
    before: str = ""
    after: str = ""

    @property
    def a(self) -> int:
        return self.begin_ctrl.end

    @property
    def b(self) -> int:
        return self.end_ctrl.start


@dataclass
class PlaceholderSlot:
    key: str
    token: str
    section: int
    p: xmlspan.Node
    start: int
    end: int
    location: str
    whole_paragraph: bool
    context: str


@dataclass
class LabelSlot:
    label: str
    norm: str
    section: int
    table: Table
    label_cell: Cell
    value_cell: Cell
    current: str


@dataclass
class RosterSlot:
    section: int
    table: Table
    header_tr: int
    columns: List[Tuple[str, int, int]]  # (라벨, 시작 열, 열 수)
    data_trs: List[int]
    empty_rows: int


@dataclass
class InlineSlot:
    label: str
    ext_label: Optional[str]
    section: int
    p: xmlspan.Node
    value_start: int
    value_end: int
    ext_start: Optional[int]
    location: str
    current: str


@dataclass
class PatternSlot:
    kind: str  # checkbox | paren | annot
    label: str
    alt_label: Optional[str]
    section: int
    p: xmlspan.Node
    start: int
    end: int
    location: str
    text: str


@dataclass
class SlotScan:
    fields: List[FieldSlot] = field(default_factory=list)
    placeholders: List[PlaceholderSlot] = field(default_factory=list)
    labels: List[LabelSlot] = field(default_factory=list)
    rosters: List[RosterSlot] = field(default_factory=list)
    inlines: List[InlineSlot] = field(default_factory=list)
    patterns: List[PatternSlot] = field(default_factory=list)
    empty_cells: List[Dict] = field(default_factory=list)
    example_cells: List[Dict] = field(default_factory=list)


def _cmd_guide(src: str, begin: xmlspan.Node) -> str:
    raw = begin.outer(src)
    m = re.search(r"Direction:wstring:\d+:(.*?)(?:\s+HelpState:|</)", raw, re.S)
    if m:
        return xmlspan.unescape(m.group(1)).strip()
    m = re.search(r'name="Command">([^<]*)<', raw)
    if m:
        return xmlspan.unescape(m.group(1)).split(";")[0].strip()
    return ""


def region_text(src: str, paras: List[xmlspan.Node], a: int, b: int) -> str:
    out: List[str] = []
    for p in paras:
        pt = ParaText(src, p)
        chunk = []
        for seg in pt.segs:
            if seg.rs >= a and seg.re <= b:
                chunk.append(seg.text)
        out.append("".join(chunk))
    return "\n".join(x for x in out).strip("\n")


def scan_fields(sec: Section) -> List[FieldSlot]:
    src = sec.src
    ends: Dict[str, xmlspan.Node] = {}
    for fe in sec.sec.iter("fieldEnd"):
        ref = fe.get(src, "beginIDRef")
        if ref:
            ends[ref] = fe
    out: List[FieldSlot] = []
    for fb in sec.sec.iter("fieldBegin"):
        typ = fb.get(src, "type") or ""
        if typ not in ("CLICK_HERE", "MAILMERGE"):
            continue
        fe = ends.get(fb.get(src, "id") or "")
        if fe is None:
            continue
        bc, ec = fb.parent, fe.parent
        if bc is None or ec is None or bc.local != "ctrl" or ec.local != "ctrl":
            continue
        pb, pe = bc.ancestor("p"), ec.ancestor("p")
        if pb is None or pe is None or pb.parent is not pe.parent:
            continue
        siblings = pb.parent.findall("p")
        i0, i1 = siblings.index(pb), siblings.index(pe)
        paras = siblings[i0:i1 + 1] if i1 >= i0 else [pb]
        name = fb.get(src, "name") or ""
        before = "".join(sg.text for sg in ParaText(src, pb).segs if sg.re <= bc.start)
        after = "".join(sg.text for sg in ParaText(src, pe).segs if sg.rs >= ec.end)
        out.append(FieldSlot(name, sec.index, fb, bc, ec, pb, pe, _cmd_guide(src, fb),
                             region_text(src, paras, bc.end, ec.start), sec.paragraph_address(pb), typ,
                             before[-30:], after[:30]))
    return out


def scan_placeholders(sec: Section) -> List[PlaceholderSlot]:
    src = sec.src
    out: List[PlaceholderSlot] = []
    for p in sec.iter_paragraphs():
        pt = ParaText(src, p)
        if "{" not in pt.text:
            continue
        for m in PLACEHOLDER_RE.finditer(pt.text):
            key = (m.group(1) or m.group(2) or "").strip()
            whole = not pt.text[:m.start()].strip() and not pt.text[m.end():].strip()
            out.append(PlaceholderSlot(key, m.group(0), sec.index, p, m.start(), m.end(),
                                       sec.paragraph_address(p), whole, pt.text[:80]))
    return out


def _tr_cells(t: Table, src: str) -> List[List[Cell]]:
    rows: Dict[int, List[Cell]] = {}
    for c in t.cells(src):
        rows.setdefault(c.tr_index, []).append(c)
    return [rows[k] for k in sorted(rows)]


def detect_header_row(t: Table, src: str) -> Optional[int]:
    """모든 칸이 짧은 라벨인 첫 행(머리행)의 tr 번호. 없으면 None."""
    rows = _tr_cells(t, src)
    for i, cells in enumerate(rows[:3]):
        if len(cells) < 2:
            continue
        texts = [c.text(src).strip() for c in cells]
        if all(tx and len(tx) <= 20 and is_label_cell(tx) for tx in texts):
            if i + 1 < len(rows):
                nxt = rows[i + 1]
                first = nxt[0].text(src).strip() if nxt else ""
                # 둘째 행 첫 칸이 라벨이면 '라벨|값' 표(구분|세부 내용)이지 명단표가 아니다 (kordoc 규칙)
                if first and is_label_cell(first):
                    return None
            return i
    return None


def scan_tables(sec: Section, scan: SlotScan) -> None:
    src = sec.src
    for t in sec.tables():
        rows = _tr_cells(t, src)
        hdr = detect_header_row(t, src) if len(rows) >= 2 else None
        covered: Set[int] = set()
        if hdr is not None and hdr + 1 < len(rows):
            header_cells = rows[hdr]
            cols = [(c.text(src).strip(), c.col, c.colspan) for c in header_cells]
            data_trs = list(range(hdr + 1, len(rows)))
            empty = sum(1 for r in data_trs if all(not c.text(src).strip() for c in rows[r]))
            scan.rosters.append(RosterSlot(sec.index, t, hdr, cols, data_trs, empty))
            for r in range(hdr + 1):
                covered.update(id(c) for c in rows[r])
        for ri, cells in enumerate(rows):
            if hdr is not None and ri <= hdr:
                continue
            for i in range(len(cells) - 1):
                lc, vc = cells[i], cells[i + 1]
                lt = lc.text(src)
                if not is_label_cell(lt) or is_keyword_label(vc.text(src)):
                    continue
                norm = normalize_label(lt)
                if not norm:
                    continue
                scan.labels.append(LabelSlot(lt.strip(), norm, sec.index, t, lc, vc, vc.text(src)))
                covered.add(id(vc))
                covered.add(id(lc))
        for c in t.cells(src):
            txt = c.text(src)
            if (not txt.strip() and id(c) not in covered and hdr is None and not c.has_nested_table()
                    and next(c.tc.iter("fieldBegin"), None) is None):
                left = t.cell(src, c.row, c.col - 1) if c.col > 0 else None
                top = t.cell(src, c.row - 1, c.col) if c.row > 0 else None
                scan.empty_cells.append({
                    "cell": c.address,
                    "left": left.text(src).strip()[:30] if left is not None else "",
                    "above": top.text(src).strip()[:30] if top is not None else "",
                })
            lines = [ln for ln in txt.split("\n") if ln.strip()]
            from .content import _MARKER_RE
            marked = [ln for ln in lines if _MARKER_RE.match(ln)]
            if len(marked) >= 2 or (lines and re.search(r"예시|\(예\)|예\)|○○|OOO", txt)):
                scan.example_cells.append({"cell": c.address, "text": txt[:200],
                                           "markers": sorted({_MARKER_RE.match(ln).group("marker") for ln in marked})})


def scan_inlines(sec: Section) -> List[InlineSlot]:
    src = sec.src
    out: List[InlineSlot] = []
    for p in sec.iter_paragraphs():
        if p.ancestor("tc") is not None:
            continue
        pt = ParaText(src, p)
        text = pt.text
        if ":" not in text and "：" not in text:
            continue
        for seg in scan_inline_segments(text):
            cur = text[seg["vs"]:seg["ve"]]
            lab_start = seg["vs"] - 1
            while lab_start > 0 and text[lab_start] not in ":：":
                lab_start -= 1
            head = text[:lab_start]
            if "{{" in cur or "${" in cur or head.rstrip().endswith("(" + seg["label"]) or \
                    re.search(r"\(\s*" + re.escape(seg["label"]) + r"\s*$", head):
                continue
            out.append(InlineSlot(seg["label"], seg.get("ext"), sec.index, p, seg["vs"], seg["ve"],
                                  seg.get("ext_start"), sec.paragraph_address(p), text[seg["vs"]:seg["ve"]]))
    return out


def scan_inline_segments(text: str) -> List[Dict]:
    labels = []
    for m in _INLINE_LABEL_RE.finditer(text):
        if text[m.end():m.end() + 1] == "/":
            continue
        labels.append({"label": m.group(2), "ext": (m.group(1) + m.group(2)) if m.group(1) else None,
                       "ext_start": m.start() if m.group(1) else None,
                       "start": m.start() + len(m.group(1)), "end": m.end()})
    segs = []
    for i, cur in enumerate(labels):
        vs = cur["end"]
        while vs < len(text) and text[vs] in " \t":
            vs += 1
        ve = labels[i + 1]["start"] if i + 1 < len(labels) else len(text)
        if ve < vs:
            ve = vs
        sep = re.search(r"[\n,;]", text[vs:ve])
        if sep:
            ve = vs + sep.start()
        if ve - vs > 100:
            ve = vs + 100
        while ve > vs and text[ve - 1].isspace():
            ve -= 1
        segs.append({"label": cur["label"], "ext": cur["ext"], "ext_start": cur["ext_start"], "vs": vs, "ve": ve})
    return segs


_CHECK_RE = re.compile(r"□(\s?)([가-힣A-Za-z]+)")
_PAREN_RE = re.compile(r"([가-힣A-Za-z]+)\(\s+\)([가-힣A-Za-z]*)")
_ANNOT_RE = re.compile(r"\(([가-힣A-Za-z]+)[:：]\s+\)")


def scan_patterns(sec: Section) -> List[PatternSlot]:
    src = sec.src
    out: List[PatternSlot] = []
    for p in sec.iter_paragraphs():
        pt = ParaText(src, p)
        text = pt.text
        if not any(ch in text for ch in "□("):
            continue
        loc = sec.paragraph_address(p)
        boxes = list(_CHECK_RE.finditer(text))
        for m in boxes:
            # '□ 추진 배경' 같은 항목부호는 체크박스가 아니다: 붙여 쓴 □남, 또는 한 줄에 여러 개인 짧은 선택지만
            if m.group(1) and not (len(boxes) >= 2 and len(m.group(2)) <= 4):
                continue
            out.append(PatternSlot("checkbox", m.group(2), None, sec.index, p, m.start(), m.start() + 1, loc, text))
        for m in _PAREN_RE.finditer(text):
            inner_s = text.index("(", m.start()) + 1
            inner_e = text.index(")", inner_s)
            out.append(PatternSlot("paren", m.group(1) + m.group(2), m.group(1), sec.index, p, inner_s, inner_e,
                                   loc, text))
        for m in _ANNOT_RE.finditer(text):
            colon = m.start() + 1 + len(m.group(1))
            out.append(PatternSlot("annot", m.group(1), None, sec.index, p, colon + 1, m.end() - 1, loc, text))
    return out


def scan_document(doc) -> List[Tuple[Section, SlotScan]]:
    out = []
    for si in range(len(doc.section_paths)):
        sec = Section(doc, si)
        scan = SlotScan()
        scan.fields = scan_fields(sec)
        scan.placeholders = scan_placeholders(sec)
        scan_tables(sec, scan)
        scan.inlines = scan_inlines(sec)
        scan.patterns = scan_patterns(sec)
        out.append((sec, scan))
    return out
