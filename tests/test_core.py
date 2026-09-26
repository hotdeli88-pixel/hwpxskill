"""Core module tests for hwpxskill."""
from pathlib import Path
import xml.etree.ElementTree as ET
import zipfile

import pytest
import hwpxskill
from hwpxskill import (
    HwpxAnalyzer,
    HwpxStyler,
    HwpxEditor,
    HwpxPackager,
    HwpxValidator,
)


def test_imports():
    """Verify all public classes and functions are importable."""
    assert HwpxAnalyzer is not None
    assert HwpxStyler is not None
    assert HwpxEditor is not None
    assert HwpxPackager is not None
    assert HwpxValidator is not None


def test_analyzer(sample_hwpx: Path):
    """Verify HwpxAnalyzer extracts structure, tables, and placeholders."""
    analyzer = HwpxAnalyzer(str(sample_hwpx))
    report = analyzer.analyze()

    assert report["summary"]["table_count"] == 1
    assert report["summary"]["section_count"] == 1

    # Check table structure
    tbl = report["tables"][0]
    assert tbl["rows"] == 3
    assert tbl["cols"] == 2
    assert len(tbl["cells"]) == 6

    # Check placeholders (contains {{REPORT_TITLE}}, {{DATE}}, ${GOAL_DESC}, empty cell)
    ph_tokens = [p.get("token") for p in report["placeholders"] if p.get("token")]
    assert "{{REPORT_TITLE}}" in ph_tokens
    assert "${GOAL_DESC}" in ph_tokens

    empty_cells = [p for p in report["placeholders"] if p.get("kind") == "empty_cell"]
    assert len(empty_cells) >= 1


def test_styler_charpr_and_borderfill(sample_header_xml: bytes):
    """Verify HwpxStyler creates new charPr and borderFill in header.xml."""
    styler = HwpxStyler()

    # Add red charPr
    new_header, char_id = styler.add_or_update_charpr(
        sample_header_xml,
        font_name="나눔고딕",
        height_pt=14.0,
        text_color="#FF0000",
        bold=True,
    )

    assert char_id is not None
    assert b'textColor="#FF0000"' in new_header
    assert b'height="1400"' in new_header
    assert 'hangul="나눔고딕"'.encode("utf-8") in new_header


    # Add borderFill with background color
    new_header_bf, bf_id = styler.add_or_update_borderfill(
        new_header,
        fill_color="#EBF3FB",
        border_type="SOLID",
        border_width="0.2 mm",
    )
    assert bf_id is not None
    assert b'faceColor="#EBF3FB"' in new_header_bf


def test_editor_fill_and_replace(sample_hwpx: Path, tmp_path: Path):
    """Verify HwpxEditor replaces placeholders and injects cell texts."""
    editor = HwpxEditor()
    out_hwpx = tmp_path / "edited.hwpx"

    fills = {
        "s0.t0.r2.c1": "1단계: 모델 설계\n2단계: 현장 적용",
    }
    replacements = {
        "{{REPORT_TITLE}}": "2026 교수학습 연간 운영 계획서",
        "{{DATE}}": "2026. 09. 26.",
        "${GOAL_DESC}": "학생 맞춤형 개념 탐구 역량 신장",
    }

    actions = editor.fill_document(
        src_hwpx=str(sample_hwpx),
        dst_hwpx=str(out_hwpx),
        fills=fills,
        replacements=replacements,
    )
    assert actions >= 4

    # Analyze the result
    analyzer = HwpxAnalyzer(str(out_hwpx))
    report = analyzer.analyze()
    tbl = report["tables"][0]

    # Verify cell text
    cell_r2_c1 = [c for c in tbl["cells"] if c["row"] == 2 and c["col"] == 1][0]
    assert "1단계: 모델 설계" in cell_r2_c1["text"]
    assert "2단계: 현장 적용" in cell_r2_c1["text"]

    cell_r1_c1 = [c for c in tbl["cells"] if c["row"] == 1 and c["col"] == 1][0]
    assert "학생 맞춤형 개념 탐구" in cell_r1_c1["text"]


def test_packager_golden_rule(sample_hwpx: Path, tmp_path: Path):
    """Verify golden packaging rules (mimetype STORED first entry)."""
    packager = HwpxPackager()
    entries = packager.unpack(sample_hwpx)
    assert "mimetype" in entries

    repacked_file = tmp_path / "repacked.hwpx"
    packager.repack(entries, repacked_file)

    with zipfile.ZipFile(repacked_file, "r") as zf:
        first_entry = zf.infolist()[0]
        assert first_entry.filename == "mimetype"
        assert first_entry.compress_type == zipfile.ZIP_STORED
        assert zf.read("mimetype") == b"application/hwp+zip"
