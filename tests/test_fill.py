import json

from hwpxskill.analyze import analyze, document_outline
from hwpxskill.core.model import Section
from hwpxskill.core.package import HwpxDocument
from hwpxskill.core.text import ParaText
from hwpxskill.fill import fill_document, format_value
from hwpxskill.validate import validate
from helpers import fixture, form_doc, reopen


def outline(doc):
    return "\n".join(document_outline(doc))


def test_analyze_finds_all_slot_kinds():
    rep = analyze(form_doc())
    s = rep["summary"]
    assert s["placeholders"] == 3 and s["label_cells"] >= 6 and s["rosters"] == 1
    assert {i["label"] for i in rep["inline_labels"]} == {"신청인", "연락처"}
    assert {c["label"] for c in rep["checkboxes"]} >= {"남", "여", "동의"}
    assert "예시" not in {c["label"] for c in rep["checkboxes"]}
    assert rep["example_cells"][0]["cell"] == "s0.t1.r1.c1"


def test_fill_all_kinds_on_generated_form():
    doc = form_doc()
    data = {
        "values": {
            "기관명": "한국교육혁신원", "작성일": "2026. 9. 28.", "신청인": "홍길동", "연락처": "02-123-4567",
            "성명": "김철수", "소속": "교육과정과", "생년월일": {"value": "19900315", "format": "date:yyyy. m. d."},
            "성별": "남", "동의": "☑", "일반통": "3", "한자": "金哲洙",
            "본문": "□ 추진 배경\n ○ 디지털 전환\n  - AI 맞춤 학습\n□ 추진 목표",
            "추진 배경": "□ 교육 환경 변화\n ○ 학령인구 감소",
            "추진 목표": "○ 모델 <eq>{3} over {4}</eq> 적용",
        },
        "rows": {"s0.t2": [{"연번": str(i), "성명": f"학생{i}", "학년": "3"} for i in range(1, 5)]},
    }
    rep = fill_document(doc, data).to_dict()
    assert rep["summary"]["skipped"] == 0 and rep["unmatched_keys"] == []
    assert rep["rows_added"] == [{"table": "s0.t2", "count": 2, "template_row": 2}]
    doc2 = reopen(doc)
    text = outline(doc2)
    for want in ("한국교육혁신원 운영 계획", "작성일: 2026. 9. 28.", "신청인: 홍길동", "연락처: 02-123-4567",
                 "1990. 3. 15.", "☑남 □여", "☑동의", "학생4", "일반(3)통", "(한자：金哲洙)", "□ 교육 환경 변화"):
        assert want in text, want
    assert validate(doc2)["ok"], validate(doc2)
    sec = doc2.text(doc2.section_paths[0])
    assert sec.count("<hp:equation") == 1 and "{3} over {4}" in sec
    assert "{{" not in text


def test_block_placeholder_becomes_paragraphs_with_hanging_indent():
    doc = form_doc()
    fill_document(doc, {"values": {"본문": "□ 가\n ○ 나\n  - 다"}})
    doc2 = reopen(doc)
    sec = Section(doc2, 0)
    texts = [ParaText(sec.src, p).text for p in sec.paragraphs()]
    assert "□\t가" in texts and "○\t나" in texts and "-\t다" in texts
    p = next(p for p in sec.paragraphs() if ParaText(sec.src, p).text == "○\t나")
    info = doc2.header.parapr(int(p.get(sec.src, "paraPrIDRef")))
    assert info["margin"]["intent"] < 0 < info["margin"]["left"]


def test_example_styles_are_reused_in_same_table():
    doc = form_doc()
    sec = Section(doc, 0)
    ex_cell = sec.table(1).cell(sec.src, 1, 1)
    ex_ppr = {ParaText(sec.src, p).text.strip()[:1]: p.get(sec.src, "paraPrIDRef") for p in ex_cell.paragraphs()}
    fill_document(doc, {"cells": {"s0.t1.r2.c1": "□ 새 항목\n ○ 새 세부"}})
    doc2 = reopen(doc)
    sec2 = Section(doc2, 0)
    cell = sec2.table(1).cell(sec2.src, 2, 1)
    got = {ParaText(sec2.src, p).text.strip()[:1]: p.get(sec2.src, "paraPrIDRef") for p in cell.paragraphs()}
    assert got == {"□": ex_ppr["□"], "○": ex_ppr["○"]}
    assert [ParaText(sec2.src, p).text for p in cell.paragraphs()] == ["□ 새 항목", " ○ 새 세부"]


def test_gian_click_here_fields_multi_paragraph_body():
    doc = HwpxDocument.open(fixture("gian_general.hwpx"))
    values = json.load(open(fixture("gian_general_values.json"), encoding="utf-8"))
    rep = fill_document(doc, {"values": values}).to_dict()
    assert rep["summary"]["filled"] == 23 and rep["summary"]["skipped"] == 0
    doc2 = reopen(doc)
    text = outline(doc2)
    assert "시행  ○○과-5678 (2026. 7. 26.)" in text
    assert "○○부장관" in text and "\t○부" not in text
    assert "가.\t사업명: 행정문서 자동화 시범사업" in text
    sec = doc2.text(doc2.section_paths[0])
    body_start = sec.index('name="본문"')
    assert sec.index('beginIDRef="1700000005"') > sec.index("다.", body_start)
    assert 'dirty="1"' in sec
    assert validate(doc2)["ok"]


def test_dry_run_style_report_and_unmatched_keys():
    doc = form_doc()
    before = doc.to_bytes()
    rep = fill_document(doc, {"values": {"기관명": "A", "없는키": "x"}}).to_dict()
    assert rep["unmatched_keys"] == ["없는키"]
    assert rep["filled"][0]["kind"] == "placeholder"
    assert before  # fill_document 자체는 저장하지 않는다


def test_array_values_are_consumed_in_order():
    doc = form_doc()
    fill_document(doc, {"values": {"기관명": ["첫째"], "작성일": "2026. 1. 2."}})
    text = outline(reopen(doc))
    assert "첫째 운영 계획" in text


def test_format_value():
    assert format_value("2026-07-05", "date:yyyy. m. d.") == "2026. 7. 5."
    assert format_value("01012345678", "phone") == "010-1234-5678"
    assert format_value("9001011234567", "rrn:masked") == "900101-1******"
    assert format_value("abc", "upper") == "ABC"
