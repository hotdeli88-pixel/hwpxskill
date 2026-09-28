"""검사기: 표기법·문체, 개인정보, 구조 검증."""
import io
import zipfile

import pytest

from hwpxskill.core.package import HwpxDocument
from hwpxskill.fill import fill_document
from hwpxskill.lint import hangul_amount, lint_document, lint_text
from hwpxskill.privacy import redact_document, scan_document, scan_text
from hwpxskill.validate import validate
from helpers import form_doc, reopen


def rules(findings):
    return {f["rule"] for f in findings}


# ── 표기법 ──
@pytest.mark.parametrize("text,rule", [
    ("2026.9.28. 회의", "DATE_NO_SPACE"), ("2026. 09. 08.", "DATE_ZERO_PAD"), ("'26. 3. 2.", "DATE_2DIGIT_YR"),
    ("오후 2시 회의", "TIME_AMPM"), ("13 : 20", "TIME_COLON_SP"), ("345천원", "MONEY_CHEONWON"),
    ("붙임: 계획서 1부.", "BUNIM_COLON"), ("2. 20.∼2. 24.까지", "KKAJI_DUP"), ("년도별 실적", "DUEUM_ERROR"),
    ("컨텐츠 개발", "LOANWORD_ERROR"), ("학부형 안내", "DISCRIMINATORY_TERM"), ("확대 — 추진", "AI_EM_DASH"),
    ("2026-09-28 시행", "DATE_HYPHEN"),
])
def test_gongmun_rules(text, rule):
    assert rule in rules(lint_text(text))


def test_correct_text_passes():
    ok = "1. 일시: 2026. 9. 28.(월) 14:00∼16:00\n2. 장소: 본관 3층 회의실\n붙임  운영 계획 1부.  끝."
    assert [f for f in lint_text(ok, document=True) if f["severity"] == "error"] == []


def test_munche_rules():
    found = rules(lint_text("□ 추진 배경\n ○ 수업 방식을 바꿔야 한다.\n ○ 참여가 늘었다.", munche=True))
    assert {"DEONTIC", "DA_ENDING"} <= found


def test_hangul_amount():
    assert hangul_amount("113560") == "일십일만삼천오백육십"


def test_lint_document_reads_filled_text():
    doc = form_doc()
    fill_document(doc, {"values": {"작성일": "2026.9.28"}})
    assert "DATE_NO_SPACE" in rules(lint_document(reopen(doc)))


# ── 개인정보 ──
def test_privacy_levels():
    f = {(x["rule"], x["level"]) for x in scan_text(
        "연락처 010-1234-5678, 주민번호 900101-1234567, 대표 02-123-4567, hong@gmail.com, a@korea.kr")}
    assert ("phone", "warning") in f and ("rrn", "warning") in f and ("email", "warning") in f
    assert ("phone", "info") in f and ("email", "info") in f


def test_privacy_rejects_invalid_numbers():
    assert scan_text("주민번호 901301-1234567") == []          # 13월
    assert scan_text("카드 1234-5678-9012-3456") == []          # Luhn 불일치
    assert scan_text("문서번호 110-123-456789") == []           # 계좌 라벨 없음


def test_redact_keeps_structure_and_removes_values():
    doc = form_doc()
    fill_document(doc, {"values": {"연락처": "010-1234-5678", "성명": "홍길동"}})
    doc = reopen(doc)
    assert any(f["level"] == "warning" for f in scan_document(doc))
    rep = redact_document(doc)
    doc2 = reopen(doc)
    assert rep["masked"] >= 1 and validate(doc2)["ok"]
    assert not [f for f in scan_document(doc2) if f["level"] == "warning"]
    assert "010-1234-5678" not in doc2.text("Preview/PrvText.txt")


# ── 구조 검증 ──
def _rewrite(doc, part, fn):
    zin = zipfile.ZipFile(io.BytesIO(doc.to_bytes()))
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        for i in zin.infolist():
            data = zin.read(i.filename)
            if i.filename == part:
                data = fn(data.decode("utf-8")).encode("utf-8")
            z.writestr(i, data)
    return HwpxDocument(out.getvalue())


def test_validate_ok_and_catches_broken_refs():
    doc = form_doc()
    assert validate(doc)["ok"]
    bad = _rewrite(doc, "Contents/section0.xml", lambda s: s.replace('charPrIDRef="0"', 'charPrIDRef="999"', 1))
    res = validate(bad)
    assert not res["ok"] and any("999" in e for e in res["errors"])


def test_validate_catches_font_name_refs_and_ns0():
    doc = form_doc()
    hdr = doc.header_path
    bad = _rewrite(doc, hdr, lambda s: s.replace('hangul="0"', 'hangul="함초롬바탕"', 1))
    assert not validate(bad)["ok"]
    bad2 = _rewrite(doc, "Contents/section0.xml", lambda s: s.replace("<hp:t>", "<ns0:t>", 1))
    assert not validate(bad2)["ok"]


def test_validate_warns_leftover_placeholders():
    res = validate(form_doc())
    assert any("{{" in w for w in res["warnings"])
