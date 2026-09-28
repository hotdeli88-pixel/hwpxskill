"""테스트 양식 생성."""
import os

from hwpxskill.core.package import HwpxDocument
from hwpxskill.core import xmlspan
from hwpxskill.core.model import Section
from hwpxskill.core.splice import Splice
from hwpxskill.skeleton import new_document, para, table

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def fixture(name: str) -> str:
    return os.path.join(FIX, name)


def form_doc() -> HwpxDocument:
    body = "".join([
        para(runs=[(2, "{{"), (0, "기관명}} 운영 계획")], para_pr=1),
        para("작성일: {{작성일}}"),
        para("신청인: ____   연락처:    "),
        para("성별 □남 □여, 동의 여부 □동의"),
        table([["성명", "", "소속", ""], ["생년월일", "", "성별", "□남 □여"]], [6000, 12000, 6000, 12000], tbl_id=1001),
        para(""),
        table([["구분", "세부 내용"],
               ["추진 배경", "□ 예시 항목\n ○ 예시 세부 내용\n  - 예시 하위 내용"],
               ["추진 목표", ""]], [8000, 28000], tbl_id=1002),
        para(""),
        table([["연번", "성명", "학년", "비고"], ["", "", "", ""], ["", "", "", ""]], [5000, 10000, 6000, 15000],
              header=True, tbl_id=1003),
        para("{{본문}}"),
        para("일반(  )통, (한자：    )"),
    ])
    return new_document(body, title="테스트 양식")


def reopen(doc: HwpxDocument) -> HwpxDocument:
    return HwpxDocument(doc.to_bytes())


# ── 표 스타일 견본 ──
def bf(doc, sides, face=None):
    parts = ['<hh:borderFill id="0" threeD="0" shadow="0" centerLine="NONE" breakCellSeparateLine="0"><hh:slash type="NONE" Crooked="0" isCounter="0"/><hh:backSlash type="NONE" Crooked="0" isCounter="0"/>']
    for s in ("leftBorder", "rightBorder", "topBorder", "bottomBorder"):
        t, w = sides[s]
        parts.append(f'<hh:{s} type="{t}" width="{w}" color="#1F3864"/>')
    parts.append('<hh:diagonal type="SOLID" width="0.1 mm" color="#000000"/>')
    if face:
        parts.append(f'<hc:fillBrush><hc:winBrush faceColor="{face}" hatchColor="#999999" alpha="0"/></hc:fillBrush>')
    parts.append('</hh:borderFill>')
    return doc.header.add("borderFill", "".join(parts))

def styled_source():
    body = para("원본 표 (스타일 견본)") + table([["구분", "1학기", "2학기", "비고"], ["국어", "90", "95", ""], ["수학", "85", "88", ""], ["합계", "175", "183", ""]], [8000, 8000, 8000, 12000], tbl_id=2001)
    doc = new_document(body)
    sec = Section(doc, 0); t = sec.table(0); src = sec.src
    hs = doc.header
    head_cp = hs.derive_charpr(0, bold=True, color="#FFFFFF", face="맑은 고딕")
    label_cp = hs.derive_charpr(0, bold=True, face="맑은 고딕")
    body_cp = hs.derive_charpr(0, face="맑은 고딕")
    center = hs.derive_parapr(0, align="CENTER", line_spacing=130)
    sp = []
    for c in t.cells(src):
        n_rows, n_cols = 4, 4
        top = ("SOLID", "0.4 mm") if c.row == 0 else ("DOUBLE_SLIM", "0.5 mm") if c.row == 1 else ("SOLID", "0.4 mm") if c.row == 3 else ("DOT", "0.12 mm")
        bottom = ("SOLID", "0.4 mm") if c.row == 3 else ("DOUBLE_SLIM", "0.5 mm") if c.row == 0 else ("SOLID", "0.4 mm") if c.row == 2 else ("DOT", "0.12 mm")
        left = ("SOLID", "0.4 mm") if c.col == 0 else ("SOLID", "0.25 mm") if c.col == 1 else ("SOLID", "0.12 mm")
        right = ("SOLID", "0.4 mm") if c.col == 3 else ("SOLID", "0.25 mm") if c.col == 0 else ("SOLID", "0.12 mm")
        face = "#1F3864" if c.row == 0 else "#FFF2CC" if c.row == 3 else "#DEEAF6" if c.col == 0 else None
        b = bf(doc, {"leftBorder": left, "rightBorder": right, "topBorder": top, "bottomBorder": bottom}, face)
        tag = xmlspan.set_attr(c.tc.open_tag(src), "borderFillIDRef", str(b))
        if c.row == 0: tag = xmlspan.set_attr(tag, "header", "1")
        sp.append(Splice(c.tc.start, c.tc.open_end, tag))
        cp = head_cp if c.row == 0 else label_cp if c.col == 0 or c.row == 3 else body_cp
        for p in c.paragraphs():
            sp.append(Splice(p.start, p.open_end, xmlspan.set_attr(p.open_tag(src), "paraPrIDRef", str(center))))
            for r in p.findall("run"):
                sp.append(Splice(r.start, r.open_end, xmlspan.set_attr(r.open_tag(src), "charPrIDRef", str(cp))))
    doc.apply(sec.path, sp)
    return doc

def plain_target():
    body = (para("대상 1: 머리행 표") + table([["학년", "반", "인원"], ["1", "3", "75"], ["2", "4", "98"]], [10000, 10000, 16000], tbl_id=3001)
            + para("대상 2: 라벨-값 표") + table([["성명", "홍길동"], ["소속", "교육과정과"], ["연락처", "044-123-4567"], ["비고", ""]], [9000, 27000], tbl_id=3002)
            + para("대상 3: 합계행이 있는 표") + table([["항목", "예산", "집행", "잔액", "비율"], ["인건비", "100", "80", "20", "80%"], ["운영비", "50", "45", "5", "90%"], ["합계", "150", "125", "25", "83%"]], [8000, 7000, 7000, 7000, 7000], tbl_id=3003))
    return new_document(body)

