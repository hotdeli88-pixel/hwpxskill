import json
import statistics

import pytest

from hwpxskill.equation import (check_script, estimate_size, find_equations, list_equations, replace_equation,
                                resolve_equation, split_eq_markup, split_word)
from hwpxskill.errors import HwpxError
from hwpxskill.fill import fill_document
from helpers import fixture, form_doc, reopen


def errors(script):
    return [f.message for f in check_script(script) if f.severity == "error"]


def warnings(script):
    return [f.message for f in check_script(script) if f.severity == "warning"]


@pytest.mark.parametrize("script", [
    "{a+b} over {2}", "sqrt {x^2 + 1}", "root {3} of {8}", "3 root5", "sum from {k=1} to {n} k^2",
    "int _{0} ^{1} x dx", "lim from {x -> 0} {sin x} over {x}", "left ( {1} over {2} right ) ^{2}",
    "int_0^2 { left{ x right} dx }", "matrix{a & b # c & d}", "x^2 overa ^2 + y^2 overb ^2 =1",
    "rmP(itA cup B) = 13 over20", "BARX -1.96 TIMES sigma", "tantheta", "-3 le x < -1", "alpha != beta",
])
def test_valid_hancom_scripts_have_no_errors(script):
    assert errors(script) == []
    assert warnings(script) == []


@pytest.mark.parametrize("script,needle", [
    ("\\frac{1}{2}", "LaTeX"), ("{a over b", "닫히지"), ("a over b}", "닫는"), ("left ( x", "짝"),
    ("over b", "분자"), ("a over", "분모"), ("$x$", "$"), ("matrix a", "{ ... }"),
])
def test_script_errors(script, needle):
    assert any(needle in m for m in errors(script)), check_script(script)


def test_typo_warning_but_not_for_glued_commands():
    assert any("sqrt" in m for m in warnings("sqr {x}"))
    assert any("alpha" in m for m in warnings("alpah + 1"))
    assert warnings("sinx + cosx") == []  # 한글은 sin x, cos x 로 읽는다


def test_split_word_like_hancom():
    assert split_word("overa") == ["over", "a"]
    assert split_word("rmAB") == ["rm", "AB"]
    assert split_word("tantheta") == ["tan", "theta"]
    assert split_word("BARX") == ["BAR", "X"]
    assert split_word("sigmaRIGHT") == ["sigma", "RIGHT"]
    assert split_word("RmP") == ["rm", "P"]
    assert split_word("dx") == ["dx"]


def test_estimate_size_matches_hancom_saved_sizes():
    rows = json.load(open(fixture("equation_sizes.json"), encoding="utf-8"))
    ew, eh = [], []
    for r in rows:
        w, h, _ = estimate_size(r["script"], r["baseUnit"])
        ew.append(abs(w - r["width"]) / r["width"])
        eh.append(abs(h - r["height"]) / r["height"])
    assert statistics.mean(ew) < 0.03 and statistics.mean(eh) < 0.04


def test_eq_markup_split():
    assert split_eq_markup("값은 <eq>x^2</eq>이다") == [("text", "값은 "), ("eq", "x^2"), ("text", "이다")]
    assert split_eq_markup("<eq block>{a} over {b}</eq>") == [("eqblock", "{a} over {b}")]


def _doc_with_equations():
    doc = form_doc()
    fill_document(doc, {"values": {"추진 목표": "○ 식 <eq>{3} over {4}</eq> 와 <eq>x^2 + 1</eq> 적용"}})
    return reopen(doc)


def test_list_find_and_replace_equation():
    doc = _doc_with_equations()
    eqs = list_equations(doc)
    assert [q["script"] for q in eqs] == ["{3} over {4}", "x^2 + 1"]
    assert find_equations(doc, "x^2+1") == [1]
    assert resolve_equation(doc, "0") == 0
    with pytest.raises(HwpxError):
        resolve_equation(doc, "없는수식")
    old_w = eqs[1]["width"]
    res = replace_equation(doc, 1, "sqrt {x^2 + 1} over {2}")
    assert res["old"] == "x^2 + 1"
    doc2 = reopen(doc)
    q = list_equations(doc2)[1]
    assert q["script"] == "sqrt {x^2 + 1} over {2}"
    assert q["width"] != old_w and q["height"] > eqs[1]["height"]  # 크기를 다시 추정
    with pytest.raises(HwpxError, match="LaTeX"):
        replace_equation(doc2, 0, "\\sqrt{2}")


def test_fill_equations_by_content():
    doc = _doc_with_equations()
    rep = fill_document(doc, {"equations": {"x^2 + 1": "x^3"}}).to_dict()
    assert rep["equations"][0]["new"] == "x^3"
    assert [q["script"] for q in list_equations(reopen(doc))] == ["{3} over {4}", "x^3"]


def test_inline_equation_uses_surrounding_font_size():
    doc = _doc_with_equations()
    assert {q["baseUnit"] for q in list_equations(doc)} == {1000}  # 주변 글자 10pt
    assert doc.text(doc.section_paths[0]).count('treatAsChar="1"') >= 2
