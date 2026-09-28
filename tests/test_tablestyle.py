from hwpxskill.core.model import Section
from hwpxskill.tablestyle import apply_table_style, extract_style
from hwpxskill.validate import validate
from helpers import plain_target, reopen, styled_source


def _cell_bf(doc, table, row, col):
    sec = Section(doc, 0)
    c = sec.table(table).cell(sec.src, row, col)
    return doc.header.borderfill(c.border_fill(sec.src)), c


def test_extract_roles_from_styled_source():
    st = extract_style(styled_source(), Section(styled_source(), 0).table(0))
    assert st.has_header and st.has_label and st.has_total
    assert st.lines["header_bottom"][0] == "DOUBLE_SLIM"
    assert st.lines["outer_top"][1] == "0.4 mm"
    assert st.lines["inner_h"][0] == "DOT"


def test_apply_cross_document_by_role():
    src, dst = styled_source(), plain_target()
    rep = apply_table_style(dst, ["s0.t0", "s0.t1", "s0.t2"], "s0.t0", source_doc=src)
    assert len(rep["log"]) == 4
    doc = reopen(dst)
    assert validate(doc)["ok"]
    head, _ = _cell_bf(doc, 0, 0, 1)
    assert head["face"] == "#1F3864" and head["sides"]["bottomBorder"][0] == "DOUBLE_SLIM"
    label, _ = _cell_bf(doc, 1, 0, 0)   # 라벨-값 표: 머리행 없이 라벨 열
    assert label["face"] == "#DEEAF6"
    total, c = _cell_bf(doc, 2, 3, 2)   # 합계행
    assert total["face"] == "#FFF2CC"
    sec = Section(doc, 0)
    run = c.paragraphs()[0].findall("run")[0]
    assert doc.header.charpr(int(run.get(sec.src, "charPrIDRef")))["bold"]
    assert doc.header.charpr(int(run.get(sec.src, "charPrIDRef")))["font"] == "맑은 고딕"
    body, _ = _cell_bf(doc, 2, 1, 2)
    assert body["face"] is None and body["sides"]["bottomBorder"][0] == "DOT"


def test_apply_same_document_reuses_ids():
    doc = styled_source()
    before = len(doc.header.ids("charPr"))
    apply_table_style(doc, ["s0.t0"], "s0.t0")
    assert len(doc.header.ids("charPr")) == before
    assert validate(reopen(doc))["ok"]
