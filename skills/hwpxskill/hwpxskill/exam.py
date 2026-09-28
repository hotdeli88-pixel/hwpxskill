"""시험지·학습지.

입력(JSON)
{
  "title": "2026학년도 2학기 기말고사", "subject": "수학", "grade": "1학년",
  "fields": ["학년", "반", "번호", "성명"],          # 머리 표 칸 (새로 만들 때)
  "notice": "※ 계산기를 사용할 수 없습니다.",        # 선택
  "columns": 2,
  "questions": [
    {"text": "<eq>{1} over {2} + {1} over {3}</eq>의 값은?", "points": 3,
     "choices": ["<eq>{1} over {6}</eq>", "<eq>{5} over {6}</eq>", "1", "<eq>{7} over {6}</eq>", "2"]},
    {"text": "다음 글을 읽고 물음에 답하시오.", "box": "지문 …", "points": 4, "space": 4}
  ]
}
- 양식(-t)이 있으면: `{{문항}}` 문단 자리, 없으면 예시 문항(번호로 시작하는 문단 + ①~⑤)을 찾아
  그 서식을 익히고 예시를 새 문항으로 바꾼다. 둘 다 없으면 본문 끝에 붙인다. 1단 양식이면 2단으로 바꾼다.
- 양식이 없으면: 내장 스타일(A4, 종이 위에 고정한 머리 표 + 문항 2단)로 새로 만든다.
  단 구분선은 `"column_line": true` 일 때만 긋는다 (머리 표를 가로지르지 않도록 기본은 끔).
- 보기 ①~⑤는 길이(수식 크기 포함)를 추정해 한 줄 / 두 줄(3+2) / 다섯 줄로 탭 위치에 맞춰 배치한다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from . import skeleton
from .content import WriteContext, run_content
from .core import xmlspan
from .core.model import Section
from .core.package import HwpxDocument
from .core.splice import Splice
from .core.text import ParaText
from .equation import check_script, estimate_size, split_eq_markup
from .errors import HwpxError

CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩"
MM = 7200 / 25.4
_STEM_RE = re.compile(r"^\s*(\d{1,2})\s*[.)]\s*\S")


@dataclass
class ExamStyles:
    stem_ppr: int
    stem_cp: int
    num_cp: int
    num_suffix: str
    num_gap: str          # "tab" 또는 그대로 쓸 공백 글자
    choice_cp: int
    choice_pprs: Dict[int, int]
    cont_ppr: int
    box_bf: int
    box_ppr: int
    blank_ppr: int
    p_tag: str
    col_width: int
    choice_indent: int
    em: int


# ── 폭 추정 ──────────────────────────────────────────────────────────────
def _text_w(s: str, em: int) -> int:
    w = 0.0
    for ch in s:
        o = ord(ch)
        if ch == " ":
            w += 0.33
        elif o < 0x80:
            w += 0.55 if not ch.isupper() else 0.68
        else:
            w += 1.0
    return int(w * em)


def rich_width(text: str, em: int) -> int:
    total = 0
    for kind, val in split_eq_markup(text):
        if kind == "text":
            total += _text_w(val, em)
        else:
            total += estimate_size(val, em)[0] + 112
    return total


def choose_layout(choices: Sequence[str], avail: int, em: int) -> int:
    """보기 한 줄에 몇 개: 5(한 줄) · 3(두 줄) · 1(다섯 줄)."""
    n = len(choices)
    widths = [rich_width(c, em) + int(1.6 * em) for c in choices]
    if n and max(widths) <= avail / n - em * 0.6:
        return n
    if n > 3 and max(widths) <= avail / 3 - em * 0.6:
        return 3
    if n > 2 and max(widths) <= avail / 2 - em * 0.6:
        return 2
    return 1


# ── 스타일 ───────────────────────────────────────────────────────────────
def _styles(doc: HwpxDocument, base_ppr: int, base_cp: int, col_width: int, p_tag: str,
            example: Optional[Dict] = None) -> ExamStyles:
    hs = doc.header
    ex = example or {}
    stem_cp = ex.get("stem_cp", base_cp)
    em = int(hs.charpr(stem_cp)["height"])
    # 한컴 내어쓰기: 첫 줄(문항 번호)은 left, 둘째 줄부터 left+|intent| = 문항 글 시작 위치
    if ex.get("stem_ppr") is not None:
        stem_ppr = ex["stem_ppr"]
        m = hs.parapr(stem_ppr)["margin"]
        text_left = m["left"] - m["intent"] if m["intent"] < 0 else m["left"] + int(em * 1.9)
    else:
        hang = int(em * 1.9)
        base_left = hs.parapr(base_ppr)["margin"]["left"]
        stem_ppr = hs.derive_parapr(base_ppr, left=base_left, intent=-hang, prev=int(em * 1.2),
                                    tab_pr=hs.ensure_auto_tab(), align="JUSTIFY", no_heading=True)
        text_left = base_left + hang
    num_cp = ex.get("num_cp")
    if num_cp is None:
        num_cp = hs.derive_charpr(stem_cp, bold=True)
    choice_cp = ex.get("choice_cp", stem_cp)
    if ex.get("choice_ppr") is not None:
        choice_base = ex["choice_ppr"]
        choice_indent = hs.parapr(choice_base)["margin"]["left"]
        keep_left = True
    else:
        choice_base = hs.derive_parapr(stem_ppr, left=text_left, intent=0, prev=int(em * 0.3), align="LEFT",
                                       no_heading=True)
        choice_indent = text_left
        keep_left = False
    avail = max(col_width - choice_indent, em * 10)
    pprs: Dict[int, int] = {}
    for n in (1, 2, 3, 4, 5):
        tab = hs.add_tab_stops([(avail * k // n, "LEFT") for k in range(1, n)]) if n > 1 else 0
        kw = {} if keep_left else {"left": choice_indent}
        pprs[n] = hs.derive_parapr(choice_base, intent=0, tab_pr=tab, align="LEFT", no_heading=True, **kw)
    cont_ppr = hs.derive_parapr(stem_ppr, left=text_left, intent=0, prev=0, no_heading=True)
    p = skeleton_prefix(doc)
    box_bf = hs.add("borderFill", skeleton._borderfill(0, "SOLID", "0.12 mm").replace("hh:", p + ":"))
    box_ppr = hs.derive_parapr(base_ppr, left=0, intent=0, prev=0, align="JUSTIFY", no_heading=True)
    blank_ppr = hs.derive_parapr(base_ppr, left=0, intent=0, prev=0, no_heading=True)
    return ExamStyles(stem_ppr, stem_cp, num_cp, ex.get("num_suffix", "."), ex.get("num_gap", "tab"), choice_cp,
                      pprs, cont_ppr, box_bf, box_ppr, blank_ppr, p_tag, col_width, choice_indent, em)


def skeleton_prefix(doc: HwpxDocument) -> str:
    for n in doc.tree(doc.header_path).iter("borderFill"):
        return n.prefix or "hh"
    return "hh"


# ── 문항 XML ──────────────────────────────────────────────────────────────
def _p(st: ExamStyles, ppr: int, runs: str) -> str:
    tag = xmlspan.set_attr(st.p_tag, "paraPrIDRef", str(ppr))
    tag = xmlspan.set_attr(tag, "pageBreak", "0")
    tag = xmlspan.set_attr(tag, "columnBreak", "0")
    name = re.match(r"<([\w:]+)", tag).group(1)
    return f"{tag}{runs}</{name}>"


def _run(ctx: WriteContext, cp: int, inner: str) -> str:
    return f'<{ctx.hp}:run charPrIDRef="{cp}">{inner}</{ctx.hp}:run>'


def _tab(ctx: WriteContext, width: int = 1000) -> str:
    return f'<{ctx.hp}:tab width="{width}" leader="0" type="1"/>'


def _points(q: Dict, fmt: str) -> str:
    pts = q.get("points")
    if pts in (None, ""):
        return ""
    n = int(pts) if float(pts) == int(float(pts)) else pts
    return " " + fmt.replace("{n}", str(n))


def question_xml(ctx: WriteContext, st: ExamStyles, q: Dict, number: str, points_fmt: str) -> str:
    hp = ctx.hp
    out: List[str] = []
    stem = str(q.get("text", "")).strip()
    lines = stem.split("\n")
    gap = _tab(ctx, int(st.em * 0.8)) if st.num_gap == "tab" else xmlspan.escape_text(st.num_gap)
    num = _run(ctx, st.num_cp, f"<{hp}:t>{xmlspan.escape_text(number + st.num_suffix)}{gap}</{hp}:t>")
    first = lines[0] + (_points(q, points_fmt) if len(lines) == 1 else "")
    out.append(_p(st, st.stem_ppr, num + _run(ctx, st.stem_cp, run_content(ctx, first, st.stem_cp))))
    for i, extra in enumerate(lines[1:]):
        txt = extra + (_points(q, points_fmt) if i == len(lines) - 2 else "")
        out.append(_p(st, st.cont_ppr, _run(ctx, st.stem_cp, run_content(ctx, txt, st.stem_cp))))
    if q.get("box"):
        out.append(box_xml(ctx, st, str(q["box"]), q.get("box_title")))
    choices = [str(c) for c in (q.get("choices") or [])]
    if choices:
        per = int(q["choice_layout"]) if str(q.get("choice_layout", "")).isdigit() else \
            choose_layout(choices, st.col_width - st.choice_indent, st.em)
        per = max(1, min(per, len(choices), 5))
        ppr = st.choice_pprs[per]
        for start in range(0, len(choices), per):
            parts: List[str] = []
            for k, c in enumerate(choices[start:start + per]):
                idx = start + k
                mark = CIRCLED[idx] if idx < len(CIRCLED) else f"({idx + 1})"
                parts.append((f"<{hp}:t>{_tab(ctx)}</{hp}:t>" if k else "")
                             + f"<{hp}:t>{mark} </{hp}:t>" + run_content(ctx, c, st.choice_cp))
            out.append(_p(st, ppr, _run(ctx, st.choice_cp, "".join(parts))))
    for _ in range(int(q.get("space") or 0)):
        out.append(_p(st, st.blank_ppr, _run(ctx, st.stem_cp, f"<{hp}:t/>")))
    return "".join(out)


def box_xml(ctx: WriteContext, st: ExamStyles, text: str, title: Optional[str] = None) -> str:
    hp = ctx.hp
    width = st.col_width - st.choice_indent
    paras = []
    if title:
        paras.append(_p(st, st.box_ppr, _run(ctx, st.num_cp, run_content(ctx, title, st.num_cp))))
    for line in text.split("\n"):
        paras.append(_p(st, st.box_ppr, _run(ctx, st.stem_cp, run_content(ctx, line, st.stem_cp))))
    eid, z = ctx.eq_ids().next()
    height = max(1, len(paras)) * int(st.em * 1.8) + 1000
    tbl = (f'<{hp}:tbl id="{eid}" zOrder="{z}" numberingType="TABLE" textWrap="TOP_AND_BOTTOM" textFlow="BOTH_SIDES" '
           f'lock="0" dropcapstyle="None" pageBreak="CELL" repeatHeader="0" rowCnt="1" colCnt="1" cellSpacing="0" '
           f'borderFillIDRef="{st.box_bf}" noAdjust="0"><{hp}:sz width="{width}" widthRelTo="ABSOLUTE" height="{height}" '
           f'heightRelTo="ABSOLUTE" protect="0"/><{hp}:pos treatAsChar="1" affectLSpacing="0" flowWithText="1" '
           f'allowOverlap="0" holdAnchorAndSO="0" vertRelTo="PARA" horzRelTo="COLUMN" vertAlign="TOP" horzAlign="LEFT" '
           f'vertOffset="0" horzOffset="0"/><{hp}:outMargin left="0" right="0" top="283" bottom="283"/>'
           f'<{hp}:inMargin left="850" right="850" top="566" bottom="566"/><{hp}:tr><{hp}:tc name="" header="0" '
           f'hasMargin="0" protect="0" editable="0" dirty="0" borderFillIDRef="{st.box_bf}"><{hp}:subList id="" '
           f'textDirection="HORIZONTAL" lineWrap="BREAK" vertAlign="TOP" linkListIDRef="0" linkListNextIDRef="0" '
           f'textWidth="0" textHeight="0" hasTextRef="0" hasNumRef="0">{"".join(paras)}</{hp}:subList>'
           f'<{hp}:cellAddr colAddr="0" rowAddr="0"/><{hp}:cellSpan colSpan="1" rowSpan="1"/>'
           f'<{hp}:cellSz width="{width}" height="{height}"/><{hp}:cellMargin left="850" right="850" top="566" '
           f'bottom="566"/></{hp}:tc></{hp}:tr></{hp}:tbl>')
    return _p(st, st.cont_ppr, _run(ctx, st.stem_cp, tbl + f"<{hp}:t/>"))


def _check_questions(questions: List[Dict]) -> List[str]:
    notes = []
    for i, q in enumerate(questions, 1):
        texts = [str(q.get("text", ""))] + [str(c) for c in q.get("choices") or []] + [str(q.get("box") or "")]
        for t in texts:
            for kind, val in split_eq_markup(t):
                if kind in ("eq", "eqblock"):
                    for f in check_script(val):
                        msg = f"{i}번 수식 `{val[:40]}` — {f.message}"
                        if f.severity == "error":
                            raise HwpxError(msg)
                        notes.append(msg)
        n = len(q.get("choices") or [])
        if n and n != 5:
            notes.append(f"{i}번: 보기가 {n}개입니다")
    return notes


# ── 새로 만들기 ────────────────────────────────────────────────────────────
def _cell(text_xml: str, col: int, row: int, colspan: int, width: int, height: int, bf: int, ppr: int,
          valign: str = "CENTER") -> str:
    return (f'<hp:tc name="" header="0" hasMargin="0" protect="0" editable="0" dirty="0" borderFillIDRef="{bf}">'
            f'<hp:subList id="" textDirection="HORIZONTAL" lineWrap="BREAK" vertAlign="{valign}" linkListIDRef="0" '
            f'linkListNextIDRef="0" textWidth="0" textHeight="0" hasTextRef="0" hasNumRef="0">'
            f'<hp:p id="0" paraPrIDRef="{ppr}" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0">{text_xml}</hp:p>'
            f'</hp:subList><hp:cellAddr colAddr="{col}" rowAddr="{row}"/><hp:cellSpan colSpan="{colspan}" rowSpan="1"/>'
            f'<hp:cellSz width="{width}" height="{height}"/><hp:cellMargin left="510" right="510" top="141" bottom="141"/></hp:tc>')


def _header_table(doc: HwpxDocument, data: Dict, content_w: int, top: int, base_pt: float, tbl_id: int) -> str:
    """시험지 머리: 종이 위쪽에 고정된 표 (두 단이 모두 이 아래에서 시작). 제목·과목·학년반번호성명·안내."""
    hs = doc.header
    title_cp = hs.derive_charpr(0, height=int(base_pt * 170), bold=True, face="함초롬돋움")
    sub_cp = hs.derive_charpr(0, height=int(base_pt * 120), face="함초롬돋움")
    label_cp = hs.derive_charpr(0, bold=True, face="함초롬돋움")
    center = hs.derive_parapr(1, align="CENTER", line_spacing=130)
    left = hs.derive_parapr(0, align="LEFT", line_spacing=130)
    none_bf = hs.add("borderFill", skeleton._borderfill(0, "NONE", "0.1 mm"))
    line_bf = hs.add("borderFill", skeleton._borderfill(0, "SOLID", "0.12 mm"))
    label_bf = hs.add("borderFill", skeleton._borderfill(0, "SOLID", "0.12 mm", "#E7E6E6"))
    fields = data.get("fields") or ["학년", "반", "번호", "성명"]
    n = max(1, len(fields)) * 2
    unit = content_w // (len(fields) * 3) if fields else content_w
    widths: List[int] = []
    for _ in fields:
        widths += [unit, unit * 2]
    if widths:
        widths[-1] += content_w - sum(widths)
    else:
        widths = [content_w]
        n = 1

    def t(text: str, cp: int) -> str:
        return f'<hp:run charPrIDRef="{cp}"><hp:t>{xmlspan.escape_text(text)}</hp:t></hp:run>'

    rows: List[str] = []
    heights: List[int] = []
    r = 0
    title = data.get("title") or ""
    sub = " ".join(x for x in (data.get("subject"), data.get("grade")) if x)
    if title:
        h = int(base_pt * 170 * 1.9)
        rows.append(_cell(t(title, title_cp), 0, r, n, content_w, h, none_bf, center))
        heights.append(h)
        r += 1
    if sub:
        h = int(base_pt * 120 * 1.9)
        rows.append(_cell(t(sub, sub_cp), 0, r, n, content_w, h, none_bf, center))
        heights.append(h)
        r += 1
    if fields:
        h = int(base_pt * 250)
        cells = []
        for i, f in enumerate(fields):
            cells.append(_cell(t(f, label_cp), 2 * i, r, 1, widths[2 * i], h, label_bf, center))
            cells.append(_cell(t("", label_cp), 2 * i + 1, r, 1, widths[2 * i + 1], h, line_bf, center))
        rows.append("".join(cells))
        heights.append(h)
        r += 1
    if data.get("notice"):
        h = int(base_pt * 100 * 1.9)
        rows.append(_cell(t(str(data["notice"]), 0), 0, r, n, content_w, h, none_bf, left))
        heights.append(h)
        r += 1
    trs = "".join(f"<hp:tr>{x}</hp:tr>" for x in rows)
    total_h = sum(heights)
    return (f'<hp:tbl id="{tbl_id}" zOrder="0" numberingType="TABLE" textWrap="TOP_AND_BOTTOM" textFlow="BOTH_SIDES" '
            f'lock="0" dropcapstyle="None" pageBreak="CELL" repeatHeader="0" rowCnt="{r}" colCnt="{n}" cellSpacing="0" '
            f'borderFillIDRef="{none_bf}" noAdjust="0"><hp:sz width="{content_w}" widthRelTo="ABSOLUTE" height="{total_h}" '
            f'heightRelTo="ABSOLUTE" protect="0"/><hp:pos treatAsChar="0" affectLSpacing="0" flowWithText="1" '
            f'allowOverlap="0" holdAnchorAndSO="0" vertRelTo="PAPER" horzRelTo="PAGE" vertAlign="TOP" horzAlign="CENTER" '
            f'vertOffset="{top}" horzOffset="0"/><hp:outMargin left="0" right="0" top="0" bottom="{int(4 * MM)}"/>'
            f'<hp:inMargin left="510" right="510" top="141" bottom="141"/>{trs}</hp:tbl>')


def _new_exam(data: Dict) -> Tuple[HwpxDocument, Dict]:
    columns = int(data.get("columns") or 2)
    base_pt = float(data.get("size") or 10)
    font = data.get("font") or "함초롬바탕"
    margins = (15, 15, 15, 15)
    doc = skeleton.new_document("", sec_pr=skeleton.sec_pr_xml(margins_mm=margins, columns=columns, col_gap_mm=8,
                                                               col_line=bool(data.get("column_line"))),
                                base_pt=base_pt, fonts=(font, "함초롬돋움"), title=data.get("title") or "시험지")
    content_w = int(round((210 - margins[0] - margins[1]) * MM))
    gap = int(round(8 * MM))
    col_w = (content_w - gap * (columns - 1)) // columns
    st = _styles(doc, 0, 0, col_w, '<hp:p id="0" paraPrIDRef="0" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0">')
    sec_path = doc.section_paths[0]
    src = doc.text(sec_path)
    ctx = WriteContext(doc, src, "hp")
    head = _header_table(doc, data, content_w, int(round(margins[2] * MM)), base_pt, ctx.eq_ids().next()[0])
    # 머리 표는 첫 문단(구역 설정 문단)에 고정 개체로 둔다
    anchor = src.index("<hp:t/></hp:run></hp:p>")
    src = src[:anchor] + head + src[anchor:]
    fmt = data.get("points_format") or "[{n}점]"
    body = [question_xml(ctx, st, q, str(q.get("number") or i), fmt)
            for i, q in enumerate(data.get("questions") or [], 1)]
    end = src.rindex("</hs:sec>")
    doc.set_text(sec_path, src[:end] + "".join(body) + src[end:])
    return doc, {"mode": "새로 만들기", "columns": columns}


# ── 양식 채우기 ───────────────────────────────────────────────────────────
def _fill_template(doc: HwpxDocument, data: Dict) -> Dict:
    notes: List[str] = []
    columns = int(data.get("columns") or 2)
    sec = Section(doc, 0)
    src = sec.src
    paras = sec.paragraphs()
    texts = [ParaText(src, p).text for p in paras]
    # 1) {{문항}} 자리
    slot = next((i for i, t in enumerate(texts) if re.fullmatch(r"\s*\{\{\s*문항\s*\}\}\s*", t)), None)
    stem_i = choice_i = None
    remove = (None, None)
    if slot is not None:
        remove = (slot, slot)
        mode = "양식 채우기({{문항}} 자리)"
    else:
        for i, t in enumerate(texts):
            if _STEM_RE.match(t):
                nxt = next((j for j in range(i + 1, min(i + 12, len(texts))) if re.search("[①②③④⑤]", texts[j])), None)
                if nxt is not None or "점]" in t:
                    stem_i, choice_i = i, nxt
                    break
        if stem_i is not None:
            last = stem_i
            for j in range(stem_i, len(texts)):
                if _STEM_RE.match(texts[j]) or re.search("[①②③④⑤]", texts[j]) or \
                        (j > stem_i and texts[j].strip() == "" and j + 1 < len(texts) and
                         (_STEM_RE.match(texts[j + 1]) or re.search("[①②③④⑤]", texts[j + 1]))):
                    last = j
                elif texts[j].strip() and j > last + 2:
                    break
            remove = (stem_i, last)
            mode = "양식 채우기(예시 문항 서식)"
        else:
            mode = "양식 채우기(본문 끝에 추가)"
    base = paras[remove[0]] if remove[0] is not None else paras[-1]
    base_ppr = int(base.get(src, "paraPrIDRef") or 0)
    bt = ParaText(src, base)
    brun = bt.run_at(0) if bt.text else (bt.runs[0] if bt.runs else None)
    base_cp = int(brun.get(src, "charPrIDRef") or 0) if brun is not None else 0
    page = _page_width(sec)
    col_n = max([int(c.get(src, "colCount") or 1) for c in sec.sec.iter("colPr")] + [1])
    need_cols = columns > 1 and col_n < columns
    use_cols = columns if (need_cols or col_n >= columns) else col_n
    gap = int(round(8 * MM))
    col_w = (page - gap * (use_cols - 1)) // use_cols
    example: Dict = {}
    if stem_i is not None:
        sp_ = paras[stem_i]
        spt = ParaText(src, sp_)
        m = re.match(r"^(\s*)(\d{1,2})(\s*[.)])([ \t]*)", spt.text)
        num_run = spt.run_at(m.start(2))
        body_run = spt.run_at(m.end())
        example["stem_ppr"] = int(sp_.get(src, "paraPrIDRef") or 0)
        if num_run is not None:
            example["num_cp"] = int(num_run.get(src, "charPrIDRef") or 0)
        if body_run is not None:
            example["stem_cp"] = int(body_run.get(src, "charPrIDRef") or 0)
        example["num_suffix"] = m.group(3).strip()
        example["num_gap"] = "tab" if "\t" in m.group(4) else (m.group(4) or " ")
        if choice_i is not None:
            cp_ = paras[choice_i]
            cpt = ParaText(src, cp_)
            ci = re.search("[①②③④⑤]", cpt.text).start()
            crun = cpt.run_at(ci)
            example["choice_ppr"] = int(cp_.get(src, "paraPrIDRef") or 0)
            if crun is not None:
                example["choice_cp"] = int(crun.get(src, "charPrIDRef") or 0)
        notes.append(f"예시 문항 서식을 따름 (s0.p{stem_i}" + (f", 보기 s0.p{choice_i})" if choice_i else ")"))
    st = _styles(doc, base_ppr, base_cp, col_w, base.open_tag(src), example)
    ctx = WriteContext(doc, src, sec.hp)
    fmt = data.get("points_format") or "[{n}점]"
    xml = "".join(question_xml(ctx, st, q, str(q.get("number") or i), fmt)
                  for i, q in enumerate(data.get("questions") or [], 1))

    def col_run(n: int, line: bool) -> str:
        return _run(ctx, base_cp, skeleton.col_pr_xml(n, 8, line).replace("hp:", ctx.hp + ":"))

    splices: List[Splice] = []
    if need_cols:
        # 단 설정은 첫 문항 문단 맨 앞에 (빈 줄을 따로 만들지 않음)
        k = xml.index(">") + 1
        xml = xml[:k] + col_run(columns, bool(data.get("column_line"))) + xml[k:]
        notes.append(f"{columns}단으로 바꿈 (문항 시작 위치부터)")
    if remove[0] is not None:
        a, b = paras[remove[0]].start, paras[remove[1]].end
        if any(c.local == "secPr" for r in paras[remove[0]].findall("run") for c in r.children):
            raise HwpxError("예시 문항이 문서 첫 문단(구역 설정)과 붙어 있어 바꿀 수 없습니다")
        splices.append(Splice(a, b, xml))
        nxt = paras[remove[1] + 1] if remove[1] + 1 < len(paras) else None
        if need_cols and nxt is not None and not any(n.local == "colPr" for n in nxt.iter()):
            # 문항 뒤 내용은 원래 단 수로 되돌린다
            splices.append(Splice(nxt.open_end, nxt.open_end, col_run(col_n, False)))
            notes.append(f"문항 뒤 내용은 {col_n}단으로 되돌림")
    else:
        last = paras[-1]
        splices.append(Splice(last.end, last.end, xml))
    doc.apply(sec.path, splices)
    return {"mode": mode, "columns": use_cols, "notes": notes}


def _page_width(sec: Section) -> int:
    src = sec.src
    pp = next(sec.sec.iter("pagePr"), None)
    if pp is None:
        return int(170 * MM)
    w = int(pp.get(src, "width") or 59528)
    h = int(pp.get(src, "height") or 84188)
    if pp.get(src, "landscape") == "NARROWLY":
        w, h = h, w
    mg = pp.find("margin")
    left = int(mg.get(src, "left") or 0) if mg is not None else 0
    right = int(mg.get(src, "right") or 0) if mg is not None else 0
    return w - left - right


def build_exam(data: Dict, template: Optional[str] = None, output: Optional[str] = None) -> Tuple[str, Dict]:
    questions = data.get("questions") or []
    if not questions:
        raise HwpxError("questions 가 비어 있습니다")
    notes = _check_questions(questions)
    if template:
        doc = HwpxDocument.open(template)
        rep = _fill_template(doc, data)
    else:
        doc, rep = _new_exam(data)
        rep["notes"] = []
    rep["notes"] = notes + rep.get("notes", [])
    rep["questions"] = len(questions)
    out = output or (template[:-5] + "_시험지.hwpx" if template else "시험지.hwpx")
    path = doc.save(out)
    return path, rep
