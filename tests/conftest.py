"""Test fixtures for hwpxskill.

Generates valid, minimal HWPX document fixtures complying with Hancom KS X 6101 OWPML standard.
"""
import zipfile
import pytest
from pathlib import Path


MANIFEST_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<ocf:container xmlns:ocf="urn:oasis:names:tc:opendocument:xmlns:container">
  <ocf:rootfiles>
    <ocf:rootfile full-path="Contents/content.hpf" media-type="application/hwp+zip"/>
  </ocf:rootfiles>
</ocf:container>""".encode("utf-8")

CONTENT_HPF = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<package xmlns="http://www.idpf.org/2007/opf/" version="2.0">
  <metadata>
    <title>HWPX Test Template</title>
  </metadata>
  <manifest>
    <item id="header" href="header.xml" media-type="application/xml"/>
    <item id="section0" href="section0.xml" media-type="application/xml"/>
  </manifest>
  <spine>
    <itemref idref="header"/>
    <itemref idref="section0"/>
  </spine>
</package>""".encode("utf-8")

HEADER_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<hh:head xmlns:ha="http://www.hancom.co.kr/hwpml/2011/app"
         xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph"
         xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section"
         xmlns:hc="http://www.hancom.co.kr/hwpml/2011/core"
         xmlns:hh="http://www.hancom.co.kr/hwpml/2011/head"
         xmlns:hhs="http://www.hancom.co.kr/hwpml/2011/history"
         xmlns:hm="http://www.hancom.co.kr/hwpml/2011/master-page"
         version="1.0">
  <hh:charProperties itemCnt="2">
    <hh:charPr id="0" height="1000" textColor="#000000">
      <hh:fontRef hangul="한컴바탕" latin="한컴바탕"/>
    </hh:charPr>
    <hh:charPr id="1" height="1200" textColor="#000000">
      <hh:fontRef hangul="HY헤드라인M" latin="HY헤드라인M"/>
      <hh:bold/>
    </hh:charPr>
  </hh:charProperties>
  <hh:paraProperties itemCnt="2">
    <hh:paraPr id="0" lineSpacing="160">
      <hh:align horizontal="JUSTIFY"/>
    </hh:paraPr>
    <hh:paraPr id="1" lineSpacing="130">
      <hh:align horizontal="CENTER"/>
    </hh:paraPr>
  </hh:paraProperties>
  <hh:borderFills itemCnt="2">
    <hh:borderFill id="0" threeD="0" shadow="0" centerLine="NONE" breakCellSeparateLine="0">
      <hh:slash type="NONE" Crooked="0" isCounter="0"/>
      <hh:backSlash type="NONE" Crooked="0" isCounter="0"/>
      <hh:leftBorder type="NONE" width="0 mm" color="#000000"/>
      <hh:rightBorder type="NONE" width="0 mm" color="#000000"/>
      <hh:topBorder type="NONE" width="0 mm" color="#000000"/>
      <hh:bottomBorder type="NONE" width="0 mm" color="#000000"/>
    </hh:borderFill>
    <hh:borderFill id="1" threeD="0" shadow="0" centerLine="NONE" breakCellSeparateLine="0">
      <hh:slash type="NONE" Crooked="0" isCounter="0"/>
      <hh:backSlash type="NONE" Crooked="0" isCounter="0"/>
      <hh:leftBorder type="SOLID" width="0.12 mm" color="#000000"/>
      <hh:rightBorder type="SOLID" width="0.12 mm" color="#000000"/>
      <hh:topBorder type="SOLID" width="0.12 mm" color="#000000"/>
      <hh:bottomBorder type="SOLID" width="0.12 mm" color="#000000"/>
      <hc:fillBrush>
        <hc:winBrush faceColor="#F0F4F8" hatchColor="#FF000000" alpha="0"/>
      </hc:fillBrush>
    </hh:borderFill>
  </hh:borderFills>
</hh:head>""".encode("utf-8")

SECTION0_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<hs:sec xmlns:ha="http://www.hancom.co.kr/hwpml/2011/app"
        xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph"
        xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section"
        xmlns:hc="http://www.hancom.co.kr/hwpml/2011/core"
        xmlns:hh="http://www.hancom.co.kr/hwpml/2011/head"
        xmlns:hhs="http://www.hancom.co.kr/hwpml/2011/history"
        xmlns:hm="http://www.hancom.co.kr/hwpml/2011/master-page">
  <hp:p id="0" paraPrIDRef="1" styleIDRef="0">
    <hp:run charPrIDRef="1"><hp:t>{{REPORT_TITLE}}</hp:t></hp:run>
  </hp:p>
  <hp:p id="1" paraPrIDRef="0" styleIDRef="0">
    <hp:run charPrIDRef="0"><hp:t>작성일: {{DATE}}</hp:t></hp:run>
  </hp:p>
  <hp:tbl id="0" zOrder="0" noAdjust="0">
    <hp:sz width="48000" height="8000"/>
    <hp:tr>
      <hp:tc name="" header="1" borderFillIDRef="1">
        <hp:subList id="" textDirection="HORIZONTAL" lineWrap="BREAK" vertAlign="CENTER">
          <hp:p id="2" paraPrIDRef="1"><hp:run charPrIDRef="1"><hp:t>구분</hp:t></hp:run></hp:p>
        </hp:subList>
        <hp:cellAddr colAddr="0" rowAddr="0"/>
        <hp:cellSz width="16000" height="4000"/>
      </hp:tc>
      <hp:tc name="" header="1" borderFillIDRef="1">
        <hp:subList id="" textDirection="HORIZONTAL" lineWrap="BREAK" vertAlign="CENTER">
          <hp:p id="3" paraPrIDRef="1"><hp:run charPrIDRef="1"><hp:t>세부 내용</hp:t></hp:run></hp:p>
        </hp:subList>
        <hp:cellAddr colAddr="1" rowAddr="0"/>
        <hp:cellSz width="32000" height="4000"/>
      </hp:tc>
    </hp:tr>
    <hp:tr>
      <hp:tc name="" header="0" borderFillIDRef="0">
        <hp:subList id="" textDirection="HORIZONTAL" lineWrap="BREAK" vertAlign="CENTER">
          <hp:p id="4" paraPrIDRef="0"><hp:run charPrIDRef="0"><hp:t>추진 목표</hp:t></hp:run></hp:p>
        </hp:subList>
        <hp:cellAddr colAddr="0" rowAddr="1"/>
        <hp:cellSz width="16000" height="4000"/>
      </hp:tc>
      <hp:tc name="" header="0" borderFillIDRef="0">
        <hp:subList id="" textDirection="HORIZONTAL" lineWrap="BREAK" vertAlign="CENTER">
          <hp:p id="5" paraPrIDRef="0"><hp:run charPrIDRef="0"><hp:t>${GOAL_DESC}</hp:t></hp:run></hp:p>
        </hp:subList>
        <hp:cellAddr colAddr="1" rowAddr="1"/>
        <hp:cellSz width="32000" height="4000"/>
      </hp:tc>
    </hp:tr>
    <hp:tr>
      <hp:tc name="" header="0" borderFillIDRef="0">
        <hp:subList id="" textDirection="HORIZONTAL" lineWrap="BREAK" vertAlign="CENTER">
          <hp:p id="6" paraPrIDRef="0"><hp:run charPrIDRef="0"><hp:t>실행 계획</hp:t></hp:run></hp:p>
        </hp:subList>
        <hp:cellAddr colAddr="0" rowAddr="2"/>
        <hp:cellSz width="16000" height="4000"/>
      </hp:tc>
      <hp:tc name="" header="0" borderFillIDRef="0">
        <hp:subList id="" textDirection="HORIZONTAL" lineWrap="BREAK" vertAlign="CENTER">
          <hp:p id="7" paraPrIDRef="0"><hp:run charPrIDRef="0"><hp:t></hp:t></hp:run></hp:p>
        </hp:subList>
        <hp:cellAddr colAddr="1" rowAddr="2"/>
        <hp:cellSz width="32000" height="4000"/>
      </hp:tc>
    </hp:tr>
  </hp:tbl>
</hs:sec>""".encode("utf-8")


def build_sample_hwpx(output_path: Path) -> Path:
    """Builds a fully compliant sample HWPX file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output_path, "w") as zf:
        # Golden Rule: mimetype must be first and uncompressed (STORED)
        zf.writestr("mimetype", b"application/hwp+zip", compress_type=zipfile.ZIP_STORED)
        zf.writestr("META-INF/manifest.xml", MANIFEST_XML, compress_type=zipfile.ZIP_DEFLATED)
        zf.writestr("Contents/content.hpf", CONTENT_HPF, compress_type=zipfile.ZIP_DEFLATED)
        zf.writestr("Contents/header.xml", HEADER_XML, compress_type=zipfile.ZIP_DEFLATED)
        zf.writestr("Contents/section0.xml", SECTION0_XML, compress_type=zipfile.ZIP_DEFLATED)
    return output_path


@pytest.fixture
def sample_hwpx(tmp_path: Path) -> Path:
    """Pytest fixture providing a sample HWPX template."""
    return build_sample_hwpx(tmp_path / "sample_template.hwpx")


@pytest.fixture
def sample_header_xml() -> bytes:
    """Pytest fixture providing raw header.xml bytes."""
    return HEADER_XML

