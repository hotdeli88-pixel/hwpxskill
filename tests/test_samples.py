"""실제 한글 저장본으로 넓게 시험 (선택).

  HWPXSKILL_SAMPLES=<hwpx 폴더> pytest -m samples

예: rhwp 저장소의 samples/ (공개 샘플). 폴더 안 .hwpx 를 모두 연다. 개인정보가 든 실제 문서는
저장소에 올리지 않는다 — 이 테스트는 로컬 폴더만 읽는다.
"""
import glob
import os

import pytest

from hwpxskill.analyze import analyze, document_outline
from hwpxskill.core.package import HwpxDocument
from hwpxskill.errors import HwpxError
from hwpxskill.lint import lint_document
from hwpxskill.privacy import scan_document
from hwpxskill.validate import validate

SAMPLES = os.environ.get("HWPXSKILL_SAMPLES", "")
FILES = sorted(glob.glob(os.path.join(SAMPLES, "**", "*.hwpx"), recursive=True))[:400] if SAMPLES else []

pytestmark = [pytest.mark.samples,
              pytest.mark.skipif(not FILES, reason="HWPXSKILL_SAMPLES 폴더가 없음")]


def _open(path):
    try:
        return HwpxDocument.open(path)
    except HwpxError as e:
        if "HWP(바이너리)" in str(e) or "암호" in str(e):
            pytest.skip(f"HWPX가 아님: {e}")
        raise


@pytest.mark.parametrize("path", FILES, ids=[os.path.basename(f) for f in FILES])
def test_sample_roundtrip_and_readers(path):
    data = open(path, "rb").read()
    doc = _open(path)
    assert doc.to_bytes() == data  # 손대지 않으면 1바이트도 바뀌지 않는다
    analyze(doc)
    document_outline(doc)
    lint_document(doc)
    scan_document(doc)
    res = validate(doc)
    assert isinstance(res["ok"], bool)
