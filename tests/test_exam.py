import re

import pytest

from hwpxskill.core.model import Section
from hwpxskill.core.package import HwpxDocument
from hwpxskill.core.text import ParaText
from hwpxskill.errors import HwpxError
from hwpxskill.exam import build_exam, choose_layout
from hwpxskill.skeleton import new_document, para
from hwpxskill.validate import validate

QUESTIONS = [
    {"text": "<eq>{1} over {2} + {1} over {3}</eq>의 값은?", "points": 3,
     "choices": ["<eq>{1} over {6}</eq>", "<eq>{2} over {5}</eq>", "<eq>{5} over {6}</eq>", "1",
                 "<eq>{7} over {6}</eq>"]},
    {"text": "다음 중 옳은 것만을 <보기>에서 있는 대로 고른 것은?", "points": 4,
     "box": "ㄱ. <eq>sqrt {4} = 2</eq>\nㄴ. <eq>(-3)^2 = -9</eq>", "box_title": "<보 기>",
     "choices": ["ㄱ", "ㄴ", "ㄱ, ㄴ", "ㄴ, ㄷ", "ㄱ, ㄴ, ㄷ"]},
    {"text": "원주율에 대한 설명으로 옳은 것은?", "points": 3,
     "choices": ["원주율의 근삿값인 3.14를 소수 둘째 자리까지 쓴 수", "순환소수 0.333…을 분수로 나타낸 수",
                 "정수 5를 7로 나눈 몫", "제곱하여 2가 되는 양수", "3을 계산한 값"]},
    {"text": "풀이 과정을 서술하시오.", "points": 5, "space": 3},
]


def _paras(doc):
    sec = Section(doc, 0)
    return sec, [ParaText(sec.src, p).text for p in sec.paragraphs()]


def test_choose_layout_by_width():
    em = 1000
    assert choose_layout(["1", "2", "3", "4", "5"], 36000, em) == 5
    assert choose_layout(["가나다라마바", "가나다라마바", "가나다", "가나", "가"], 36000, em) == 3
    long = ["가" * 20] * 5
    assert choose_layout(long, 36000, em) == 1


def test_new_exam_structure(tmp_path):
    out = tmp_path / "exam.hwpx"
    path, rep = build_exam({"title": "기말고사", "subject": "수학", "fields": ["반", "번호", "성명"],
                            "questions": QUESTIONS}, output=str(out))
    assert rep["questions"] == 4 and rep["columns"] == 2
    doc = HwpxDocument.open(path)
    assert validate(doc)["ok"], validate(doc)
    sec, texts = _paras(doc)
    stems = [t for t in texts if re.match(r"^\d\.\t", t)]
    assert [s[:2] for s in stems] == ["1.", "2.", "3.", "4."]
    assert any(t.startswith("① ") and "\t② " in t and "\t⑤ " in t for t in texts)  # 한 줄 배치
    assert any(t.startswith("① 원주율") and "②" not in t for t in texts)  # 긴 보기는 한 줄에 하나
    assert "[5점]" in "".join(texts)
    src = sec.src
    assert re.search(r'<hp:colPr[^>]*colCount="2"', src)
    head = re.search(r"<hp:tbl [^>]*>.*?<hp:pos [^>]*>", src, re.S).group(0)
    assert 'treatAsChar="0"' in head and 'vertRelTo="PAPER"' in head
    assert src.count("<hp:equation") == 7  # 1번 문항·보기 5개 + 2번 상자 2개
    # 문항 번호(굵게) 뒤 문항 글은 내어쓰기로 정렬
    stem_p = next(p for p in sec.paragraphs() if ParaText(src, p).text.startswith("3.\t"))
    m = doc.header.parapr(int(stem_p.get(src, "paraPrIDRef")))["margin"]
    assert m["intent"] < 0


def test_column_line_is_opt_in(tmp_path):
    q = [{"text": "문제", "choices": ["1", "2", "3", "4", "5"]}]
    p1, _ = build_exam({"questions": q}, output=str(tmp_path / "a.hwpx"))
    p2, _ = build_exam({"questions": q, "column_line": True}, output=str(tmp_path / "b.hwpx"))

    def col_line(path):
        d = HwpxDocument.open(path)
        src = d.text(d.section_paths[0])
        i = src.index("<hp:colPr")
        return "<hp:colLine" in src[i:src.index("</hp:ctrl>", i)]

    assert not col_line(p1) and col_line(p2)


def test_template_example_question_is_replaced_with_its_style(tmp_path):
    base, _ = build_exam({"questions": QUESTIONS[:3]}, output=str(tmp_path / "t.hwpx"))
    src_doc = HwpxDocument.open(base)
    sec0, _ = _paras(src_doc)
    ex = next(p for p in sec0.paragraphs() if ParaText(sec0.src, p).text.startswith("1.\t"))
    ex_ppr = ex.get(sec0.src, "paraPrIDRef")
    new_q = [{"text": "다음 중 소수인 것은?", "points": 2, "choices": ["1", "4", "7", "9", "15"]},
             {"text": "<eq>2^3 times 2^2</eq>의 값은?", "points": 3,
              "choices": ["<eq>2^5</eq>", "<eq>2^6</eq>", "<eq>4^5</eq>", "<eq>4^6</eq>", "<eq>2^{10}</eq>"]}]
    path, rep = build_exam({"questions": new_q}, template=base, output=str(tmp_path / "filled.hwpx"))
    assert "예시 문항" in rep["mode"]
    doc = HwpxDocument.open(path)
    assert validate(doc)["ok"], validate(doc)
    sec, texts = _paras(doc)
    stems = [t for t in texts if re.match(r"^\d\.\t", t)]
    assert len(stems) == 2 and stems[0].startswith("1.\t다음 중 소수인")
    assert not any("원주율" in t or "보 기" in t for t in texts)  # 예시 문항은 모두 지워짐
    p = next(p for p in sec.paragraphs() if ParaText(sec.src, p).text.startswith("1.\t"))
    assert p.get(sec.src, "paraPrIDRef") == ex_ppr


def test_template_slot_in_one_column_document(tmp_path):
    body = para("2026학년도 수학 학습지", para_pr=1) + para("{{문항}}") + para("수고했습니다.")
    tpl = tmp_path / "slot.hwpx"
    new_document(body).save(str(tpl))
    path, rep = build_exam({"questions": QUESTIONS[:2]}, template=str(tpl), output=str(tmp_path / "out.hwpx"))
    assert "{{문항}}" in rep["mode"] and rep["columns"] == 2
    doc = HwpxDocument.open(path)
    assert validate(doc)["ok"], validate(doc)
    sec, texts = _paras(doc)
    assert "{{문항}}" not in "".join(texts)
    filled = [t for t in texts if t.strip()]
    assert filled[0] == "2026학년도 수학 학습지" and filled[-1] == "수고했습니다."
    assert len(re.findall(r'colCount="2"', sec.src)) == 1


def test_latex_in_question_is_rejected():
    with pytest.raises(HwpxError, match="LaTeX|\\\\frac"):
        build_exam({"questions": [{"text": "<eq>\\frac{1}{2}</eq>"}]}, output="/nonexistent/x.hwpx")
