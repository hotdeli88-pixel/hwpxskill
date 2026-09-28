"""새 HWPX 문서 골격 (한컴 저장본과 같은 파트 구성).

시험지 새로 만들기와 테스트 양식 생성에 쓴다. 스타일은 최소 정의만 두고, 필요한 글자·문단
모양은 HeaderStyles.derive_*()로 파생한다.
"""
from __future__ import annotations

from typing import List, Sequence, Tuple

from .core.package import HwpxDocument
from .core.zipio import build_zip

_NS = ('xmlns:ha="http://www.hancom.co.kr/hwpml/2011/app" '
       'xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph" '
       'xmlns:hp10="http://www.hancom.co.kr/hwpml/2016/paragraph" '
       'xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section" '
       'xmlns:hc="http://www.hancom.co.kr/hwpml/2011/core" '
       'xmlns:hh="http://www.hancom.co.kr/hwpml/2011/head" '
       'xmlns:hhs="http://www.hancom.co.kr/hwpml/2011/history" '
       'xmlns:hm="http://www.hancom.co.kr/hwpml/2011/master-page" '
       'xmlns:hpf="http://www.hancom.co.kr/schema/2011/hpf" '
       'xmlns:dc="http://purl.org/dc/elements/1.1/" '
       'xmlns:opf="http://www.idpf.org/2007/opf/" '
       'xmlns:ooxmlchart="http://www.hancom.co.kr/hwpml/2016/ooxmlchart" '
       'xmlns:hwpunitchar="http://www.hancom.co.kr/hwpml/2016/HwpUnitChar" '
       'xmlns:epub="http://www.idpf.org/2007/ops" '
       'xmlns:config="urn:oasis:names:tc:opendocument:xmlns:config:1.0"')
_DECL = '<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>'
LANGS = ("HANGUL", "LATIN", "HANJA", "JAPANESE", "OTHER", "SYMBOL", "USER")
MM = 7200 / 25.4


def _fontfaces(fonts: Sequence[str]) -> str:
    out = [f'<hh:fontfaces itemCnt="{len(LANGS)}">']
    for lang in LANGS:
        out.append(f'<hh:fontface lang="{lang}" fontCnt="{len(fonts)}">')
        for i, face in enumerate(fonts):
            out.append(f'<hh:font id="{i}" face="{face}" type="TTF" isEmbedded="0"><hh:typeInfo familyType="FCAT_GOTHIC" '
                       'weight="6" proportion="4" contrast="0" strokeVariation="1" armStyle="1" letterform="1" '
                       'midline="1" xHeight="1"/></hh:font>')
        out.append("</hh:fontface>")
    out.append("</hh:fontfaces>")
    return "".join(out)


def _border(side: str, typ: str = "NONE", width: str = "0.1 mm") -> str:
    return f'<hh:{side} type="{typ}" width="{width}" color="#000000"/>'


def _borderfill(bid: int, typ: str, width: str, face: str = "none") -> str:
    sides = "".join(_border(s, typ, width) for s in ("leftBorder", "rightBorder", "topBorder", "bottomBorder"))
    return (f'<hh:borderFill id="{bid}" threeD="0" shadow="0" centerLine="NONE" breakCellSeparateLine="0">'
            '<hh:slash type="NONE" Crooked="0" isCounter="0"/><hh:backSlash type="NONE" Crooked="0" isCounter="0"/>'
            f'{sides}<hh:diagonal type="SOLID" width="0.1 mm" color="#000000"/>'
            f'<hc:fillBrush><hc:winBrush faceColor="{face}" hatchColor="#999999" alpha="0"/></hc:fillBrush></hh:borderFill>')


def _charpr(cid: int, height: int, font: int, bold: bool = False) -> str:
    langs = " ".join(f'{a}="{font}"' for a in ("hangul", "latin", "hanja", "japanese", "other", "symbol", "user"))
    hundred = " ".join(f'{a}="100"' for a in ("hangul", "latin", "hanja", "japanese", "other", "symbol", "user"))
    zero = " ".join(f'{a}="0"' for a in ("hangul", "latin", "hanja", "japanese", "other", "symbol", "user"))
    return (f'<hh:charPr id="{cid}" height="{height}" textColor="#000000" shadeColor="none" useFontSpace="0" '
            f'useKerning="0" symMark="NONE" borderFillIDRef="2"><hh:fontRef {langs}/><hh:ratio {hundred}/>'
            f'<hh:spacing {zero}/><hh:relSz {hundred}/><hh:offset {zero}/>' + ("<hh:bold/>" if bold else "") +
            '<hh:underline type="NONE" shape="SOLID" color="#000000"/><hh:strikeout shape="NONE" color="#000000"/>'
            '<hh:outline type="NONE"/><hh:shadow type="NONE" color="#B2B2B2" offsetX="10" offsetY="10"/></hh:charPr>')


def _margin(intent: int = 0, left: int = 0, prev: int = 0, nxt: int = 0, scale: int = 1) -> str:
    def v(x: int) -> int:
        return x * scale
    return (f'<hh:margin><hc:intent value="{v(intent)}" unit="HWPUNIT"/><hc:left value="{v(left)}" unit="HWPUNIT"/>'
            f'<hc:right value="0" unit="HWPUNIT"/><hc:prev value="{v(prev)}" unit="HWPUNIT"/>'
            f'<hc:next value="{v(nxt)}" unit="HWPUNIT"/></hh:margin>')


def parapr_xml(pid: int, align: str = "JUSTIFY", line: int = 160, tab: int = 0, intent: int = 0, left: int = 0,
               prev: int = 0, nxt: int = 0, keep_word: bool = True) -> str:
    brk = "BREAK_WORD" if keep_word else "KEEP_WORD"
    ls = f'<hh:lineSpacing type="PERCENT" value="{line}" unit="HWPUNIT"/>'
    return (f'<hh:paraPr id="{pid}" tabPrIDRef="{tab}" condense="0" fontLineHeight="0" snapToGrid="1" '
            f'suppressLineNumbers="0" checked="0"><hh:align horizontal="{align}" vertical="BASELINE"/>'
            f'<hh:heading type="NONE" idRef="0" level="0"/><hh:breakSetting breakLatinWord="KEEP_WORD" '
            f'breakNonLatinWord="{brk}" widowOrphan="0" keepWithNext="0" keepLines="0" pageBreakBefore="0" '
            f'lineWrap="BREAK"/><hh:autoSpacing eAsianEng="0" eAsianNum="0"/>'
            f'<hp:switch><hp:case hp:required-namespace="http://www.hancom.co.kr/hwpml/2016/HwpUnitChar">'
            f'{_margin(intent, left, prev, nxt)}{ls}</hp:case><hp:default>{_margin(intent, left, prev, nxt, 2)}{ls}'
            f'</hp:default></hp:switch><hh:border borderFillIDRef="2" offsetLeft="0" offsetRight="0" offsetTop="0" '
            f'offsetBottom="0" connect="0" ignoreMargin="0"/></hh:paraPr>')


def header_xml(fonts: Sequence[str] = ("함초롬바탕", "함초롬돋움"), base_pt: float = 10.0, line: int = 160) -> str:
    h = int(round(base_pt * 100))
    chars = [_charpr(0, h, 0), _charpr(1, h, 1), _charpr(2, h, 0, bold=True), _charpr(3, h, 1, bold=True)]
    paras = [parapr_xml(0, "JUSTIFY", line), parapr_xml(1, "CENTER", line), parapr_xml(2, "LEFT", line),
             parapr_xml(3, "RIGHT", line)]
    tabs = ('<hh:tabProperties itemCnt="3"><hh:tabPr id="0" autoTabLeft="0" autoTabRight="0"/>'
            '<hh:tabPr id="1" autoTabLeft="1" autoTabRight="0"/><hh:tabPr id="2" autoTabLeft="0" autoTabRight="1"/>'
            '</hh:tabProperties>')
    heads = "".join(
        f'<hh:paraHead start="1" level="{lv}" align="LEFT" useInstWidth="1" autoIndent="1" widthAdjust="0" '
        f'textOffsetType="PERCENT" textOffset="50" numFormat="{fmt}" charPrIDRef="4294967295" checkable="0">{txt}</hh:paraHead>'
        for lv, fmt, txt in [(1, "DIGIT", "^1."), (2, "HANGUL_SYLLABLE", "^2."), (3, "DIGIT", "^3)"),
                             (4, "HANGUL_SYLLABLE", "^4)"), (5, "DIGIT", "(^5)"), (6, "HANGUL_SYLLABLE", "(^6)"),
                             (7, "CIRCLED_DIGIT", "^7")])
    numberings = f'<hh:numberings itemCnt="1"><hh:numbering id="1" start="0">{heads}</hh:numbering></hh:numberings>'
    styles = ('<hh:styles itemCnt="1"><hh:style id="0" type="PARA" name="바탕글" engName="Normal" paraPrIDRef="0" '
              'charPrIDRef="0" nextStyleIDRef="0" langID="1042" lockForm="0"/></hh:styles>')
    borders = ('<hh:borderFills itemCnt="3">' + _borderfill(1, "NONE", "0.1 mm") + _borderfill(2, "NONE", "0.1 mm")
               + _borderfill(3, "SOLID", "0.12 mm") + '</hh:borderFills>')
    return (f'{_DECL}<hh:head {_NS} version="1.4" secCnt="1"><hh:beginNum page="1" footnote="1" endnote="1" pic="1" '
            f'tbl="1" equation="1"/><hh:refList>{_fontfaces(fonts)}{borders}'
            f'<hh:charProperties itemCnt="{len(chars)}">{"".join(chars)}</hh:charProperties>{tabs}{numberings}'
            f'<hh:paraProperties itemCnt="{len(paras)}">{"".join(paras)}</hh:paraProperties>{styles}</hh:refList>'
            '<hh:compatibleDocument targetProgram="HWP201X"><hh:layoutCompatibility/></hh:compatibleDocument>'
            '<hh:docOption><hh:linkinfo path="" pageInherit="0" footnoteInherit="0"/></hh:docOption>'
            '<hh:trackchageConfig flags="56"/></hh:head>')


def sec_pr_xml(width_mm: float = 210, height_mm: float = 297, margins_mm: Tuple[float, float, float, float] = (20, 20, 15, 15),
               header_mm: float = 10, footer_mm: float = 10, columns: int = 1, col_gap_mm: float = 8,
               col_line: bool = False) -> str:
    """첫 문단 첫 run에 들어갈 secPr + colPr. margins_mm = (왼, 오른, 위, 아래)."""
    l, r, t, b = (int(round(x * MM)) for x in margins_mm)
    w, h = int(round(width_mm * MM)), int(round(height_mm * MM))
    return ('<hp:secPr id="" textDirection="HORIZONTAL" spaceColumns="1134" tabStop="8000" tabStopVal="4000" '
            'tabStopUnit="HWPUNIT" outlineShapeIDRef="1" memoShapeIDRef="0" textVerticalWidthHead="0" masterPageCnt="0">'
            '<hp:grid lineGrid="0" charGrid="0" wonggojiFormat="0"/><hp:startNum pageStartsOn="BOTH" page="0" pic="0" '
            'tbl="0" equation="0"/><hp:visibility hideFirstHeader="0" hideFirstFooter="0" hideFirstMasterPage="0" '
            'border="SHOW_ALL" fill="SHOW_ALL" hideFirstPageNum="0" hideFirstEmptyLine="0" showLineNumber="0"/>'
            '<hp:lineNumberShape restartType="0" countBy="0" distance="0" startNumber="0"/>'
            f'<hp:pagePr landscape="WIDELY" width="{w}" height="{h}" gutterType="LEFT_ONLY">'
            f'<hp:margin header="{int(header_mm * MM)}" footer="{int(footer_mm * MM)}" gutter="0" left="{l}" right="{r}" '
            f'top="{t}" bottom="{b}"/></hp:pagePr>'
            '<hp:footNotePr><hp:autoNumFormat type="DIGIT" userChar="" prefixChar="" suffixChar=")" supscript="0"/>'
            '<hp:noteLine length="-1" type="SOLID" width="0.12 mm" color="#000000"/><hp:noteSpacing betweenNotes="283" '
            'belowLine="567" aboveLine="850"/><hp:numbering type="CONTINUOUS" newNum="1"/><hp:placement '
            'place="EACH_COLUMN" beneathText="0"/></hp:footNotePr><hp:endNotePr><hp:autoNumFormat type="DIGIT" '
            'userChar="" prefixChar="" suffixChar=")" supscript="0"/><hp:noteLine length="14692344" type="SOLID" '
            'width="0.12 mm" color="#000000"/><hp:noteSpacing betweenNotes="0" belowLine="567" aboveLine="850"/>'
            '<hp:numbering type="CONTINUOUS" newNum="1"/><hp:placement place="END_OF_DOCUMENT" beneathText="0"/>'
            '</hp:endNotePr><hp:pageBorderFill type="BOTH" borderFillIDRef="1" textBorder="PAPER" headerInside="0" '
            'footerInside="0" fillArea="PAPER"><hp:offset left="1417" right="1417" top="1417" bottom="1417"/>'
            '</hp:pageBorderFill></hp:secPr>' + col_pr_xml(columns, col_gap_mm, col_line))


def col_pr_xml(columns: int = 1, gap_mm: float = 8, line: bool = False) -> str:
    gap = int(round(gap_mm * MM)) if columns > 1 else 0
    inner = '<hp:colLine type="SOLID" width="0.12 mm" color="#000000"/>' if line and columns > 1 else ""
    if inner:
        return (f'<hp:ctrl><hp:colPr id="" type="NEWSPAPER" layout="LEFT" colCount="{columns}" sameSz="1" '
                f'sameGap="{gap}">{inner}</hp:colPr></hp:ctrl>')
    return f'<hp:ctrl><hp:colPr id="" type="NEWSPAPER" layout="LEFT" colCount="{columns}" sameSz="1" sameGap="{gap}"/></hp:ctrl>'


def section_xml(body: str, sec_pr: str = "") -> str:
    """body = 첫 문단 뒤에 이어질 문단들. 첫 문단은 secPr를 담는 빈 문단."""
    first = (f'<hp:p id="0" paraPrIDRef="0" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0">'
             f'<hp:run charPrIDRef="0">{sec_pr or sec_pr_xml()}</hp:run><hp:run charPrIDRef="0"><hp:t/></hp:run></hp:p>')
    return f'{_DECL}<hs:sec {_NS}>{first}{body}</hs:sec>'


def package_files(header: str, sections: List[str], title: str = "", preview: str = "") -> List[Tuple[str, bytes, bool]]:
    manifest_items = ['<opf:item id="header" href="Contents/header.xml" media-type="application/xml"/>']
    spine = ['<opf:itemref idref="header" linear="yes"/>']
    for i in range(len(sections)):
        manifest_items.append(f'<opf:item id="section{i}" href="Contents/section{i}.xml" media-type="application/xml"/>')
        spine.append(f'<opf:itemref idref="section{i}" linear="yes"/>')
    manifest_items.append('<opf:item id="settings" href="settings.xml" media-type="application/xml"/>')
    hpf = (f'{_DECL}<opf:package {_NS} version="" unique-identifier="" id=""><opf:metadata><opf:title>{title}'
           '</opf:title><opf:language>ko</opf:language><opf:meta name="creator" content="text">hwpxskill</opf:meta>'
           f'</opf:metadata><opf:manifest>{"".join(manifest_items)}</opf:manifest><opf:spine>{"".join(spine)}'
           '</opf:spine></opf:package>')
    container = (f'{_DECL}<ocf:container xmlns:ocf="urn:oasis:names:tc:opendocument:xmlns:container" '
                 'xmlns:hpf="http://www.hancom.co.kr/schema/2011/hpf"><ocf:rootfiles><ocf:rootfile '
                 'full-path="Contents/content.hpf" media-type="application/hwpml-package+xml"/><ocf:rootfile '
                 'full-path="Preview/PrvText.txt" media-type="text/plain"/></ocf:rootfiles></ocf:container>')
    version = (f'{_DECL}<hv:HCFVersion xmlns:hv="http://www.hancom.co.kr/hwpml/2011/version" tagetApplication="WORDPROCESSOR" '
               'major="5" minor="1" micro="0" buildNumber="1" os="1" xmlVersion="1.2" application="Hancom Office Hangul" '
               'appVersion="11, 0, 0, 2129 WIN32LEWindows_8"/>')
    settings = (f'{_DECL}<ha:HWPApplicationSetting xmlns:ha="http://www.hancom.co.kr/hwpml/2011/app" '
                'xmlns:config="urn:oasis:names:tc:opendocument:xmlns:config:1.0"><ha:CaretPosition listIDRef="0" '
                'paraIDRef="0" pos="0"/></ha:HWPApplicationSetting>')
    manifest = f'{_DECL}<odf:manifest xmlns:odf="urn:oasis:names:tc:opendocument:xmlns:manifest:1.0"/>'
    files: List[Tuple[str, bytes, bool]] = [
        ("mimetype", b"application/hwp+zip", False),
        ("version.xml", version.encode("utf-8"), False),
        ("Contents/header.xml", header.encode("utf-8"), True),
    ]
    for i, s in enumerate(sections):
        files.append((f"Contents/section{i}.xml", s.encode("utf-8"), True))
    files += [
        ("Preview/PrvText.txt", (preview or title)[:1000].encode("utf-8"), True),
        ("settings.xml", settings.encode("utf-8"), True),
        ("Contents/content.hpf", hpf.encode("utf-8"), True),
        ("META-INF/container.xml", container.encode("utf-8"), True),
        ("META-INF/manifest.xml", manifest.encode("utf-8"), True),
    ]
    return files


def new_document(body: str = "", *, sec_pr: str = "", fonts: Sequence[str] = ("함초롬바탕", "함초롬돋움"),
                 base_pt: float = 10.0, line: int = 160, title: str = "") -> HwpxDocument:
    data = build_zip(package_files(header_xml(fonts, base_pt, line), [section_xml(body, sec_pr)], title))
    return HwpxDocument(data)


# ── 본문 조각 (테스트 양식·시험지용) ────────────────────────────────────────
def esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def para(text: str = "", para_pr: int = 0, char_pr: int = 0, runs: Sequence[Tuple[int, str]] = ()) -> str:
    body = "".join(f'<hp:run charPrIDRef="{cp}"><hp:t>{esc(t)}</hp:t></hp:run>' for cp, t in runs) if runs else \
        f'<hp:run charPrIDRef="{char_pr}"><hp:t>{esc(text)}</hp:t></hp:run>'
    return f'<hp:p id="0" paraPrIDRef="{para_pr}" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0">{body}</hp:p>'


def table(rows: Sequence[Sequence[object]], widths: Sequence[int], row_h: int = 1800, border_fill: int = 3,
          header: bool = False, tbl_id: int = 1000, cell_para_pr: int = 0, cell_char_pr: int = 0) -> str:
    """셀 값: 문자열(여러 줄은 문단) 또는 (문자열, colSpan, rowSpan) 또는 None(병합으로 덮인 칸)."""
    n_rows, n_cols = len(rows), len(widths)
    trs = []
    for r, row in enumerate(rows):
        tcs = []
        c = 0
        for cell in row:
            if cell is None:
                c += 1
                continue
            text, cs, rs = (cell, 1, 1) if isinstance(cell, str) else cell
            w = sum(widths[c:c + cs])
            paras = "".join(
                f'<hp:p id="0" paraPrIDRef="{cell_para_pr}" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0">'
                f'<hp:run charPrIDRef="{cell_char_pr}"><hp:t>{esc(line)}</hp:t></hp:run></hp:p>'
                for line in str(text).split("\n"))
            tcs.append(f'<hp:tc name="" header="{1 if header and r == 0 else 0}" hasMargin="0" protect="0" editable="0" '
                       f'dirty="0" borderFillIDRef="{border_fill}"><hp:subList id="" textDirection="HORIZONTAL" '
                       'lineWrap="BREAK" vertAlign="CENTER" linkListIDRef="0" linkListNextIDRef="0" textWidth="0" '
                       f'textHeight="0" hasTextRef="0" hasNumRef="0">{paras}</hp:subList><hp:cellAddr colAddr="{c}" '
                       f'rowAddr="{r}"/><hp:cellSpan colSpan="{cs}" rowSpan="{rs}"/><hp:cellSz width="{w}" '
                       f'height="{row_h * rs}"/><hp:cellMargin left="510" right="510" top="141" bottom="141"/></hp:tc>')
            c += cs
        trs.append("<hp:tr>" + "".join(tcs) + "</hp:tr>")
    total_w = sum(widths)
    return (f'<hp:p id="0" paraPrIDRef="0" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0"><hp:run charPrIDRef="0">'
            f'<hp:tbl id="{tbl_id}" zOrder="0" numberingType="TABLE" textWrap="TOP_AND_BOTTOM" textFlow="BOTH_SIDES" '
            f'lock="0" dropcapstyle="None" pageBreak="CELL" repeatHeader="{1 if header else 0}" rowCnt="{n_rows}" '
            f'colCnt="{n_cols}" cellSpacing="0" borderFillIDRef="{border_fill}" noAdjust="0">'
            f'<hp:sz width="{total_w}" widthRelTo="ABSOLUTE" height="{row_h * n_rows}" heightRelTo="ABSOLUTE" protect="0"/>'
            '<hp:pos treatAsChar="1" affectLSpacing="0" flowWithText="1" allowOverlap="0" holdAnchorAndSO="0" '
            'vertRelTo="PARA" horzRelTo="COLUMN" vertAlign="TOP" horzAlign="LEFT" vertOffset="0" horzOffset="0"/>'
            '<hp:outMargin left="0" right="0" top="0" bottom="0"/><hp:inMargin left="510" right="510" top="141" '
            f'bottom="141"/>{"".join(trs)}</hp:tbl><hp:t/></hp:run></hp:p>')
