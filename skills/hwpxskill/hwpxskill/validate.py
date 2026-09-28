"""HWPX 구조 검사.

- 패키지: mimetype 첫 엔트리·무압축·값, 필수 파트, manifest 파일 존재
- XML: 모든 XML 파트가 짝이 맞는지, 한컴 표준 네임스페이스 접두어(hp·hs·hh·hc)인지
- 스타일 참조: 본문의 charPrIDRef·paraPrIDRef·borderFillIDRef·styleIDRef가 header.xml에 있는지
- header itemCnt·fontCnt가 실제 개수와 같은지, secCnt가 섹션 수와 같은지
- 표: rowCnt·colCnt와 실제 셀 주소, 누름틀 짝
- 편집 흔적: 남은 {{자리표시}}, 채우지 않은 누름틀, 수식 스크립트 문법
"""
from __future__ import annotations

import re
from typing import Dict, List

from .core import xmlspan
from .core.model import Section
from .core.text import ParaText
from .equation import check_script
from .errors import HwpxError
from .forms import PLACEHOLDER_RE

REQUIRED = ["mimetype", "Contents/content.hpf", "Contents/header.xml"]
STD_PREFIX = {
    "http://www.hancom.co.kr/hwpml/2011/paragraph": "hp",
    "http://www.hancom.co.kr/hwpml/2011/section": "hs",
    "http://www.hancom.co.kr/hwpml/2011/head": "hh",
    "http://www.hancom.co.kr/hwpml/2011/core": "hc",
}
_REF_KINDS = {"charPrIDRef": "charPr", "paraPrIDRef": "paraPr", "borderFillIDRef": "borderFill",
              "styleIDRef": "style"}


def validate(doc) -> Dict:
    errors: List[str] = []
    warnings: List[str] = []
    info: List[str] = []
    arc = doc.archive
    entries = arc.entries
    if not entries or entries[0].name != "mimetype":
        errors.append("mimetype이 ZIP의 첫 번째 파일이 아닙니다 (한글이 열지 못할 수 있음)")
    elif entries[0].method != 0:
        errors.append("mimetype이 압축되어 있습니다 (무압축이어야 함)")
    names = set(arc.names())
    for req in REQUIRED + doc.section_paths:
        if req not in names:
            errors.append(f"필수 파일이 없습니다: {req}")
    # manifest가 가리키는 파일
    try:
        hpf = doc.text(doc.hpf_path)
        for m in re.finditer(r"<[\w:]*item\b[^>]*>", hpf):
            href = xmlspan.get_attr(m.group(0), "href")
            if href and doc._resolve(href) not in names:
                warnings.append(f"content.hpf가 없는 파일을 가리킵니다: {href}")
    except KeyError:
        pass
    # XML 형식·접두어
    xml_parts = [n for n in arc.names() if n.endswith((".xml", ".hpf", ".rdf"))]
    for n in xml_parts:
        try:
            src = doc.text(n)
            root = xmlspan.parse(src)
        except (HwpxError, UnicodeDecodeError) as e:
            errors.append(f"{n}: XML이 깨졌습니다 — {e}")
            continue
        if n.startswith("Contents/") and n.endswith(".xml"):
            prefixes = xmlspan.namespace_prefixes(src, root)
            for uri, std in STD_PREFIX.items():
                got = prefixes.get(uri)
                if got is not None and got != std:
                    errors.append(f"{n}: 네임스페이스 접두어가 '{got}'입니다 (한컴 표준은 '{std}')")
            if re.search(r"<ns\d+:", src[:5000]):
                errors.append(f"{n}: ns0/ns1 같은 자동 생성 접두어가 있습니다 (한글에서 깨질 수 있음)")
    if errors:
        return _result(errors, warnings, info)
    # header 정합성
    hs = doc.header
    counts = {k: set(hs.ids(k)) for k in ("charPr", "paraPr", "borderFill", "style", "tabPr")}
    hsrc = doc.text(doc.header_path)
    hroot = doc.tree(doc.header_path)
    for cont in ("charProperties", "paraProperties", "borderFills", "styles", "tabProperties", "numberings"):
        node = next(hroot.iter(cont), None)
        if node is None:
            continue
        declared = node.get(hsrc, "itemCnt")
        actual = len([c for c in node.children])
        if declared is not None and declared.isdigit() and int(declared) != actual:
            errors.append(f"header.xml {cont} itemCnt={declared}인데 실제 {actual}개")
    for ff in hroot.iter("fontface"):
        declared = ff.get(hsrc, "fontCnt")
        actual = len(ff.findall("font"))
        if declared is not None and declared.isdigit() and int(declared) != actual:
            errors.append(f"header.xml fontface({ff.get(hsrc, 'lang')}) fontCnt={declared}인데 실제 {actual}개")
    head = xmlspan.document_element(hroot)
    sec_cnt = head.get(hsrc, "secCnt")
    if sec_cnt and sec_cnt.isdigit() and int(sec_cnt) != len(doc.section_paths):
        warnings.append(f"header.xml secCnt={sec_cnt}, 섹션 {len(doc.section_paths)}개")
    for lang_node in hroot.iter("fontRef"):
        for attr, val in lang_node.attrs(hsrc).items():
            if not val.lstrip("-").isdigit():
                errors.append(f"글꼴 참조(fontRef {attr}=\"{val}\")가 숫자 id가 아닙니다")
                break
    # 본문
    placeholders = 0
    empty_fields: List[str] = []
    for si in range(len(doc.section_paths)):
        sec = Section(doc, si)
        src = sec.src
        missing: Dict[str, set] = {}
        for m in re.finditer(r'\s(charPrIDRef|paraPrIDRef|borderFillIDRef|styleIDRef)="(\d+)"', src):
            kind = _REF_KINDS[m.group(1)]
            val = int(m.group(2))
            if kind == "charPr" and val == 4294967295:
                continue
            if val not in counts[kind]:
                if kind == "borderFill" and val == 0:
                    continue
                missing.setdefault(m.group(1), set()).add(val)
        for k, vals in missing.items():
            errors.append(f"s{si}: header.xml에 없는 {k} {sorted(vals)[:10]}")
        for t in sec.tables():
            cells = t.cells(src)
            rc, cc = t.node.get(src, "rowCnt"), t.node.get(src, "colCnt")
            if rc and rc.isdigit() and cells:
                max_r = max(c.row + c.rowspan for c in cells)
                if max_r != int(rc):
                    errors.append(f"{t.id}: rowCnt={rc}인데 셀 주소상 {max_r}행")
            if cc and cc.isdigit() and cells:
                max_c = max(c.col + c.colspan for c in cells)
                if max_c != int(cc):
                    warnings.append(f"{t.id}: colCnt={cc}인데 셀 주소상 {max_c}열")
            seen = set()
            for c in cells:
                key = (c.row, c.col)
                if key in seen:
                    errors.append(f"{t.id}: 셀 주소 r{c.row}.c{c.col} 가 중복됩니다")
                seen.add(key)
        begins = {fb.get(src, "id") for fb in sec.sec.iter("fieldBegin")}
        ends = {fe.get(src, "beginIDRef") for fe in sec.sec.iter("fieldEnd")}
        if begins - ends:
            errors.append(f"s{si}: 짝이 없는 누름틀 시작 {sorted(x for x in begins - ends if x)[:5]}")
        for p in sec.iter_paragraphs():
            pt = ParaText(src, p)
            if "{" in pt.text:
                for m in PLACEHOLDER_RE.finditer(pt.text):
                    placeholders += 1
                    if placeholders <= 20:
                        warnings.append(f"채우지 않은 자리표시 {m.group(0)} @ {sec.paragraph_address(p)}")
        from .forms import scan_fields
        for f in scan_fields(sec):
            if not f.current.strip():
                empty_fields.append(f.name)
        for eq in sec.sec.iter("equation"):
            sc = eq.find("script")
            if sc is None:
                continue
            script = xmlspan.unescape(sc.inner(src))
            for fnd in check_script(script):
                if fnd.severity == "error":
                    warnings.append(f"수식 `{script[:40]}` — {fnd.message}")
    if empty_fields:
        info.append("비어 있는 누름틀: " + ", ".join(empty_fields[:30]))
    return _result(errors, warnings, info)


def _result(errors: List[str], warnings: List[str], info: List[str]) -> Dict:
    return {"ok": not errors, "errors": errors, "warnings": warnings, "info": info}


def format_result(res: Dict) -> str:
    lines = ["구조: 정상" if res["ok"] else f"구조: 오류 {len(res['errors'])}건"]
    lines += [f"  [오류] {e}" for e in res["errors"]]
    lines += [f"  [경고] {w}" for w in res["warnings"]]
    lines += [f"  [참고] {i}" for i in res["info"]]
    return "\n".join(lines)
