import io
import zipfile

import pytest

from hwpxskill.core import xmlspan
from hwpxskill.core.package import HwpxDocument
from hwpxskill.core.splice import Splice, apply_splices
from hwpxskill.core.text import ParaText, inline_xml
from hwpxskill.errors import HwpxError
from helpers import fixture, form_doc, reopen


def test_xmlspan_positions_and_attrs():
    src = '<a x="1"><b y=\'2\'>t&amp;x</b><c/></a>'
    root = xmlspan.parse(src)
    a = xmlspan.document_element(root)
    b, c = a.children
    assert a.attrs(src) == {"x": "1"}
    assert b.get(src, "y") == "2"
    assert b.inner(src) == "t&amp;x"
    assert c.self_closing
    assert xmlspan.unescape(b.inner(src)) == "t&x"


def test_xmlspan_rejects_broken_xml():
    with pytest.raises(HwpxError):
        xmlspan.parse("<a><b></a>")


def test_set_attr_preserves_rest_of_tag():
    tag = '<hp:p id="0" paraPrIDRef="3" styleIDRef="0">'
    assert xmlspan.set_attr(tag, "paraPrIDRef", "7") == '<hp:p id="0" paraPrIDRef="7" styleIDRef="0">'
    assert xmlspan.set_attr('<x a="1"/>', "b", "2") == '<x a="1" b="2"/>'


def test_splices_apply_and_detect_overlap():
    assert apply_splices("abcdef", [Splice(1, 3, "X"), Splice(4, 4, "Y")]) == "aXdYef"
    with pytest.raises(HwpxError):
        apply_splices("abcdef", [Splice(1, 4, ""), Splice(2, 5, "")])


def test_untouched_roundtrip_is_byte_identical():
    data = open(fixture("gian_general.hwpx"), "rb").read()
    assert HwpxDocument(data).to_bytes() == data


def test_edit_keeps_mimetype_first_and_other_entries_raw():
    path = fixture("gian_simple.hwpx")
    data = open(path, "rb").read()
    doc = HwpxDocument(data)
    sec = doc.section_paths[0]
    doc.set_text(sec, doc.text(sec).replace("작성일", "작성일", 1))  # 같은 내용 → 변경 없음
    assert doc.to_bytes() == data
    doc.set_text(sec, doc.text(sec) + " ")
    out = doc.to_bytes()
    zf = zipfile.ZipFile(io.BytesIO(out))
    first = zf.infolist()[0]
    assert first.filename == "mimetype" and first.compress_type == zipfile.ZIP_STORED
    orig = zipfile.ZipFile(io.BytesIO(data))
    assert [i.filename for i in zf.infolist()] == [i.filename for i in orig.infolist()]
    assert zf.read("Contents/header.xml") == orig.read("Contents/header.xml")
    assert zf.testzip() is None


def test_paratext_replace_across_runs_and_linebreak():
    src = ('<hp:p xmlns:hp="u"><hp:run charPrIDRef="1"><hp:t>이름: {{</hp:t></hp:run>'
           '<hp:run charPrIDRef="2"><hp:t>NAME}}</hp:t></hp:run></hp:p>')
    p = xmlspan.document_element(xmlspan.parse(src))
    pt = ParaText(src, p)
    assert pt.text == "이름: {{NAME}}"
    start = pt.text.index("{{")
    out = apply_splices(src, pt.replace(start, len(pt.text), inline_xml("홍길동 & <김>")))
    p2 = xmlspan.document_element(xmlspan.parse(out))
    assert ParaText(out, p2).text == "이름: 홍길동 & <김>"
    src2 = '<hp:p xmlns:hp="u"><hp:run charPrIDRef="0"><hp:t>첫줄<hp:lineBreak/>{{D}}</hp:t></hp:run></hp:p>'
    p = xmlspan.document_element(xmlspan.parse(src2))
    pt = ParaText(src2, p)
    assert pt.text == "첫줄\n{{D}}"
    out = apply_splices(src2, pt.replace(3, 8, "2026"))
    assert "<hp:lineBreak/>2026</hp:t>" in out


def test_header_derive_parapr_doubles_default_branch_and_dedups():
    doc = form_doc()
    hs = doc.header
    base_n = len(hs.ids("paraPr"))
    a = hs.derive_parapr(0, left=3000, intent=-1500)
    b = hs.derive_parapr(0, left=3000, intent=-1500)
    assert a == b == base_n
    xml = hs.xml("paraPr", a)
    assert '<hc:left value="3000"' in xml and '<hc:left value="6000"' in xml
    assert hs.parapr(a)["margin"]["left"] == 3000
    doc2 = reopen(doc)
    h = doc2.text(doc2.header_path)
    assert f'<hh:paraProperties itemCnt="{base_n + 1}">' in h


def test_derive_charpr_uses_font_ids_not_names():
    doc = form_doc()
    cid = doc.header.derive_charpr(0, height=1400, bold=True, face="맑은 고딕")
    info = doc.header.charpr(cid)
    assert info["bold"] and info["height"] == 1400 and info["font"] == "맑은 고딕"
    xml = doc.header.xml("charPr", cid)
    assert 'hangul="맑은 고딕"' not in xml
    doc2 = reopen(doc)
    assert doc2.header.charpr(cid)["font"] == "맑은 고딕"


def test_hwp_binary_is_rejected_with_guidance():
    with pytest.raises(HwpxError, match="convert"):
        HwpxDocument(b"\xd0\xcf\x11\xe0" + b"\x00" * 100)


def test_encrypted_hwpx_is_rejected_with_guidance():
    import io, zipfile
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(zipfile.ZipInfo("mimetype"), "application/hwp+zip")
        z.writestr("META-INF/manifest.xml", '<odf:manifest><odf:file-entry><odf:encryption-data/></odf:file-entry></odf:manifest>')
    with pytest.raises(HwpxError, match="암호"):
        HwpxDocument(buf.getvalue())
