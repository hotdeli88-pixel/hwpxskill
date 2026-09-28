"""header.xml 스타일 정의 읽기와 추가.

- 읽기: 글자 모양(charPr)·문단 모양(paraPr)·테두리/배경(borderFill)·탭(tabPr)·글꼴
- 쓰기: 기존 정의를 복제해 일부만 바꾼 새 정의를 추가한다. 같은 정의가 이미 있으면
  새로 만들지 않고 그 id를 쓴다. 추가분은 commit() 때 한 번에 삽입하고 itemCnt를 고친다.
- `hp:switch`(HwpUnitChar)로 이중 저장된 여백·탭 위치는 `hp:default` 쪽이 2배 값이다.
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

from ..errors import HwpxError
from . import xmlspan
from .elem import ElemEditor, canonical
from .splice import Splice, apply_splices

KIND_CONTAINER = {
    "charPr": "charProperties",
    "paraPr": "paraProperties",
    "borderFill": "borderFills",
    "tabPr": "tabProperties",
    "style": "styles",
    "numbering": "numberings",
    "bullet": "bullets",
}
LANGS = ("HANGUL", "LATIN", "HANJA", "JAPANESE", "OTHER", "SYMBOL", "USER")
LANG_ATTR = {"HANGUL": "hangul", "LATIN": "latin", "HANJA": "hanja", "JAPANESE": "japanese",
             "OTHER": "other", "SYMBOL": "symbol", "USER": "user"}
MARGIN_KEYS = ("intent", "left", "right", "prev", "next")


def _int(v: Optional[str], default: int = 0) -> int:
    try:
        return int(float(v)) if v is not None else default
    except ValueError:
        return default


class HeaderStyles:
    def __init__(self, doc):
        self.doc = doc
        self.path = doc.header_path
        self._parsed = False
        self._pending_items: Dict[str, List[Tuple[int, str]]] = {}
        self._pending_fonts: Dict[str, List[Tuple[int, str, str]]] = {}
        self._canon: Dict[str, Dict[str, int]] = {}
        self._pending_xml: Dict[Tuple[str, int], str] = {}

    # ── 파싱 ──
    def invalidate(self) -> None:
        self._parsed = False

    @property
    def pending(self) -> bool:
        return any(self._pending_items.values()) or any(self._pending_fonts.values())

    @property
    def src(self) -> str:
        return self.doc.text(self.path)

    def _ensure(self) -> None:
        if self._parsed:
            return
        src = self.src
        root = self.doc.tree(self.path)
        self._containers: Dict[str, xmlspan.Node] = {}
        self._items: Dict[str, Dict[int, xmlspan.Node]] = {}
        for kind, cname in KIND_CONTAINER.items():
            cont = next(root.iter(cname), None)
            items: Dict[int, xmlspan.Node] = {}
            if cont is not None:
                self._containers[kind] = cont
                for it in cont.findall(kind):
                    iid = it.get(src, "id")
                    if iid is not None and iid.lstrip("-").isdigit():
                        items[int(iid)] = it
            self._items[kind] = items
        self._fontfaces: Dict[str, xmlspan.Node] = {}
        self._fonts: Dict[str, Dict[int, str]] = {}
        self._font_nodes: Dict[str, Dict[int, xmlspan.Node]] = {}
        for ff in root.iter("fontface"):
            lang = ff.get(src, "lang") or ""
            self._fontfaces[lang] = ff
            self._fonts[lang] = {}
            self._font_nodes[lang] = {}
            for f in ff.findall("font"):
                fid = _int(f.get(src, "id"), -1)
                self._fonts[lang][fid] = f.get(src, "face") or ""
                self._font_nodes[lang][fid] = f
        if not self._canon:
            for kind, items in self._items.items():
                self._canon[kind] = {canonical(n.outer(src)): i for i, n in items.items()}
        self._parsed = True

    # ── 원문 접근 ──
    def ids(self, kind: str) -> List[int]:
        self._ensure()
        out = list(self._items[kind].keys())
        out += [i for i, _ in self._pending_items.get(kind, [])]
        return sorted(out)

    def has(self, kind: str, iid: int) -> bool:
        self._ensure()
        return iid in self._items.get(kind, {}) or (kind, iid) in self._pending_xml

    def xml(self, kind: str, iid: int) -> str:
        self._ensure()
        if (kind, iid) in self._pending_xml:
            return self._pending_xml[(kind, iid)]
        node = self._items.get(kind, {}).get(iid)
        if node is None:
            raise HwpxError(f"header.xml에 {kind} id={iid} 가 없습니다")
        return node.outer(self.src)

    def font_face(self, lang: str, fid: int) -> Optional[str]:
        self._ensure()
        face = self._fonts.get(lang, {}).get(fid)
        if face is None:
            for pid, pface, _ in self._pending_fonts.get(lang, []):
                if pid == fid:
                    return pface
        return face

    def font_xml(self, lang: str, fid: int) -> Optional[str]:
        self._ensure()
        n = self._font_nodes.get(lang, {}).get(fid)
        if n is not None:
            return n.outer(self.src)
        for pid, _, x in self._pending_fonts.get(lang, []):
            if pid == fid:
                return x
        return None

    # ── 읽기 전용 정보 ──
    def charpr(self, iid: int) -> Dict:
        ed = ElemEditor(self.xml("charPr", iid))
        el = ed.el
        info: Dict = {
            "id": iid,
            "height": _int(ed.get(el, "height"), 1000),
            "textColor": ed.get(el, "textColor") or "#000000",
            "shadeColor": ed.get(el, "shadeColor") or "none",
            "borderFillIDRef": _int(ed.get(el, "borderFillIDRef"), 0),
        }
        info["bold"] = ed.first("bold") is not None or ed.get(el, "bold") in ("1", "true")
        info["italic"] = ed.first("italic") is not None or ed.get(el, "italic") in ("1", "true")
        ul = ed.first("underline")
        info["underline"] = ul is not None and (ed.get(ul, "type") or "NONE") != "NONE"
        so = ed.first("strikeout")
        info["strikeout"] = so is not None and (ed.get(so, "shape") or "NONE") not in ("NONE", "3D")
        fonts: Dict[str, str] = {}
        fr = ed.first("fontRef")
        if fr is not None:
            for lang, attr in LANG_ATTR.items():
                fid = ed.get(fr, attr)
                if fid is not None and fid.isdigit():
                    fonts[lang] = self.font_face(lang, int(fid)) or ""
        info["fonts"] = fonts
        info["font"] = fonts.get("HANGUL") or fonts.get("LATIN") or ""
        for k in ("ratio", "spacing", "relSz", "offset"):
            n = ed.first(k)
            info[k] = _int(ed.get(n, "hangul"), 100 if k in ("ratio", "relSz") else 0) if n is not None else None
        return info

    def parapr(self, iid: int) -> Dict:
        ed = ElemEditor(self.xml("paraPr", iid))
        el = ed.el
        info: Dict = {"id": iid, "tabPrIDRef": _int(ed.get(el, "tabPrIDRef"), 0)}
        al = ed.first("align")
        info["align"] = (ed.get(al, "horizontal") if al is not None else None) or "JUSTIFY"
        info["valign"] = (ed.get(al, "vertical") if al is not None else None) or "BASELINE"
        hd = ed.first("heading")
        info["heading"] = (ed.get(hd, "type") if hd is not None else None) or "NONE"
        margins = {k: 0 for k in MARGIN_KEYS}
        margin = _preferred(ed, "margin")
        if margin is not None:
            scale = 2 if _in_default_branch(margin) else 1
            for c in margin.children:
                if c.local in MARGIN_KEYS:
                    margins[c.local] = _int(ed.get(c, "value")) // scale
        info["margin"] = margins
        ls = _preferred(ed, "lineSpacing")
        info["lineSpacing"] = {"type": (ed.get(ls, "type") if ls is not None else None) or "PERCENT",
                               "value": _int(ed.get(ls, "value") if ls is not None else None, 160)}
        bs = ed.first("breakSetting")
        info["breakNonLatinWord"] = ed.get(bs, "breakNonLatinWord") if bs is not None else None
        return info

    def borderfill(self, iid: int) -> Dict:
        ed = ElemEditor(self.xml("borderFill", iid))
        sides: Dict[str, Tuple[str, str, str]] = {}
        for side in ("leftBorder", "rightBorder", "topBorder", "bottomBorder", "diagonal"):
            n = ed.first(side)
            if n is not None:
                sides[side] = (ed.get(n, "type") or "NONE", ed.get(n, "width") or "0.1 mm", ed.get(n, "color") or "#000000")
        fb = ed.first("fillBrush")
        wb = ed.first("winBrush")
        face = ed.get(wb, "faceColor") if wb is not None else None
        if face in (None, "none", "None"):
            face = None
        return {"id": iid, "sides": sides, "face": face,
                "fill_xml": fb.outer(ed.src) if fb is not None else None}

    def tabpr(self, iid: int) -> Dict:
        ed = ElemEditor(self.xml("tabPr", iid))
        items = []
        for ti in ed.nodes("tabItem"):
            scale = 2 if _in_default_branch(ti) else 1
            if scale == 2 and any(a.local == "switch" for a in ti.ancestors()):
                continue
            items.append({"pos": _int(ed.get(ti, "pos")) // scale, "type": ed.get(ti, "type"),
                          "leader": ed.get(ti, "leader")})
        return {"id": iid, "autoTabLeft": ed.get(ed.el, "autoTabLeft") == "1",
                "autoTabRight": ed.get(ed.el, "autoTabRight") == "1", "items": items}

    def style(self, iid: int) -> Dict:
        ed = ElemEditor(self.xml("style", iid))
        el = ed.el
        return {"id": iid, "name": ed.get(el, "name"), "engName": ed.get(el, "engName"),
                "type": ed.get(el, "type"), "paraPrIDRef": _int(ed.get(el, "paraPrIDRef")),
                "charPrIDRef": _int(ed.get(el, "charPrIDRef"))}

    def style_by_name(self, name: str) -> Optional[Dict]:
        for iid in self.ids("style"):
            st = self.style(iid)
            if st["name"] == name or st["engName"] == name:
                return st
        return None

    # ── 추가 ──
    def add(self, kind: str, xml: str) -> int:
        """정의를 추가하고 id를 돌려준다. 같은 정의가 이미 있으면 그 id."""
        self._ensure()
        key = canonical(xml)
        canon = self._canon.setdefault(kind, {})
        if key in canon:
            return canon[key]
        if kind not in self._containers:
            raise HwpxError(f"header.xml에 {KIND_CONTAINER[kind]} 목록이 없어 {kind}를 추가할 수 없습니다")
        existing = self.ids(kind)
        new_id = (max(existing) + 1) if existing else (1 if kind == "borderFill" else 0)
        head_end = xml.find(">")
        head = xmlspan.set_attr(xml[:head_end + 1], "id", str(new_id))
        new_xml = head + xml[head_end + 1:]
        self._pending_items.setdefault(kind, []).append((new_id, new_xml))
        self._pending_xml[(kind, new_id)] = new_xml
        canon[key] = new_id
        return new_id

    def font_id(self, lang: str, face: str) -> Optional[int]:
        self._ensure()
        for fid, f in self._fonts.get(lang, {}).items():
            if f == face:
                return fid
        for fid, f, _ in self._pending_fonts.get(lang, []):
            if f == face:
                return fid
        return None

    def ensure_font(self, face: str, lang: str, template_xml: Optional[str] = None) -> int:
        """글꼴 목록(lang)에 face가 없으면 추가하고 id를 돌려준다."""
        fid = self.font_id(lang, face)
        if fid is not None:
            return fid
        self._ensure()
        if lang not in self._fontfaces:
            raise HwpxError(f"header.xml에 {lang} 글꼴 목록이 없습니다")
        existing = list(self._fonts.get(lang, {}).keys()) + [i for i, _, _ in self._pending_fonts.get(lang, [])]
        new_id = max(existing) + 1 if existing else 0
        if template_xml is None:
            nodes = self._font_nodes.get(lang, {})
            template_xml = next(iter(nodes.values())).outer(self.src) if nodes else (
                '<hh:font id="0" face="" type="TTF" isEmbedded="0"/>')
        head_end = template_xml.find(">")
        head = xmlspan.set_attr(template_xml[:head_end + 1], "id", str(new_id))
        head = xmlspan.set_attr(head, "face", face)
        new_xml = head + template_xml[head_end + 1:]
        new_xml = re.sub(r"<(\w+:)?substFont\b[^>]*/>", "", new_xml)
        self._pending_fonts.setdefault(lang, []).append((new_id, face, new_xml))
        return new_id

    # ── 파생 정의 ──
    def derive_parapr(self, base_id: int, *, align: Optional[str] = None, left: Optional[int] = None,
                      intent: Optional[int] = None, right: Optional[int] = None, prev: Optional[int] = None,
                      next_: Optional[int] = None, line_spacing: Optional[int] = None,
                      tab_pr: Optional[int] = None, no_heading: bool = False,
                      keep_word: Optional[bool] = None) -> int:
        ed = ElemEditor(self.xml("paraPr", base_id))
        if tab_pr is not None:
            ed.set(ed.el, "tabPrIDRef", str(tab_pr))
        if align is not None:
            for al in ed.nodes("align"):
                ed.set(al, "horizontal", align)
        if no_heading:
            for hd in ed.nodes("heading"):
                ed.set(hd, "type", "NONE")
                ed.set(hd, "idRef", "0")
                ed.set(hd, "level", "0")
        if keep_word is not None:
            for bs in ed.nodes("breakSetting"):
                ed.set(bs, "breakNonLatinWord", "KEEP_WORD" if keep_word else "BREAK_WORD")
        vals = {"intent": intent, "left": left, "right": right, "prev": prev, "next": next_}
        for margin in ed.nodes("margin"):
            scale = 2 if _in_default_branch(margin) else 1
            for c in margin.children:
                v = vals.get(c.local)
                if v is not None:
                    ed.set(c, "value", str(int(v) * scale))
        if line_spacing is not None:
            for ls in ed.nodes("lineSpacing"):
                ed.set(ls, "type", "PERCENT")
                ed.set(ls, "value", str(int(line_spacing)))
        return self.add("paraPr", ed.result())

    def derive_charpr(self, base_id: int, *, height: Optional[int] = None, bold: Optional[bool] = None,
                      italic: Optional[bool] = None, color: Optional[str] = None,
                      face: Optional[str] = None, underline: Optional[bool] = None) -> int:
        ed = ElemEditor(self.xml("charPr", base_id))
        el = ed.el
        if height is not None:
            ed.set(el, "height", str(int(height)))
        if color is not None:
            ed.set(el, "textColor", color)
        if face is not None:
            fr = ed.first("fontRef")
            if fr is not None:
                for lang, attr in LANG_ATTR.items():
                    if lang in self._fontfaces_langs():
                        ed.set(fr, attr, str(self.ensure_font(face, lang)))
        for flag, tag in ((bold, "bold"), (italic, "italic")):
            if flag is None:
                continue
            ed.set(el, tag, None)  # 속성형 표기는 정리하고 요소형으로 통일
            cur = ed.first(tag)
            if flag and cur is None:
                anchor = ed.first("underline") or ed.first("strikeout") or ed.first("outline") or ed.first("shadow")
                if anchor is not None:
                    ed.insert_before(anchor, f"<{el.prefix + ':' if el.prefix else ''}{tag}/>")
                else:
                    ed.append_child(el, f"<{el.prefix + ':' if el.prefix else ''}{tag}/>")
            elif not flag and cur is not None:
                ed.remove(cur)
        if underline is not None:
            ul = ed.first("underline")
            if ul is not None:
                ed.set(ul, "type", "BOTTOM" if underline else "NONE")
            elif underline:
                p = el.prefix + ":" if el.prefix else ""
                ed.append_child(el, f'<{p}underline type="BOTTOM" shape="SOLID" color="#000000"/>')
        return self.add("charPr", ed.result())

    def _fontfaces_langs(self) -> List[str]:
        self._ensure()
        return list(self._fontfaces.keys())

    def ensure_auto_tab(self) -> int:
        """내어쓰기용 자동 탭(autoTabLeft=1) tabPr id. 없으면 만든다."""
        for iid in self.ids("tabPr"):
            info = self.tabpr(iid)
            if info["autoTabLeft"] and not info["items"]:
                return iid
        p = self._prefix_of("tabPr")
        return self.add("tabPr", f'<{p}tabPr id="0" autoTabLeft="1" autoTabRight="0"/>')

    def add_tab_stops(self, stops: List[Tuple[int, str]]) -> int:
        """탭 위치 목록[(HWPUNIT, LEFT|CENTER|RIGHT)]으로 tabPr을 만든다 (hp:switch 이중 저장)."""
        p = self._prefix_of("tabPr")
        hp = self.doc.prefix(self.path, "http://www.hancom.co.kr/hwpml/2011/paragraph") or "hp"
        parts = []
        for pos, typ in stops:
            parts.append(
                f'<{hp}:switch><{hp}:case {hp}:required-namespace="http://www.hancom.co.kr/hwpml/2016/HwpUnitChar">'
                f'<{p}tabItem pos="{int(pos)}" type="{typ}" leader="NONE" unit="HWPUNIT"/></{hp}:case>'
                f'<{hp}:default><{p}tabItem pos="{int(pos) * 2}" type="{typ}" leader="NONE"/></{hp}:default></{hp}:switch>')
        return self.add("tabPr", f'<{p}tabPr id="0" autoTabLeft="0" autoTabRight="0">{"".join(parts)}</{p}tabPr>')

    def _prefix_of(self, kind: str) -> str:
        self._ensure()
        cont = self._containers.get(kind)
        if cont is not None and cont.prefix:
            return cont.prefix + ":"
        return "hh:"

    # ── 다른 문서에서 가져오기 ──
    def import_charpr(self, other: "HeaderStyles", iid: int) -> int:
        ed = ElemEditor(other.xml("charPr", iid))
        fr = ed.first("fontRef")
        if fr is not None:
            for lang, attr in LANG_ATTR.items():
                v = ed.get(fr, attr)
                if v is None or not v.isdigit():
                    continue
                face = other.font_face(lang, int(v))
                if face is None or lang not in self._fontfaces_langs():
                    continue
                ed.set(fr, attr, str(self.ensure_font(face, lang, other.font_xml(lang, int(v)))))
        bf = ed.get(ed.el, "borderFillIDRef")
        if bf is not None and bf.isdigit() and other.has("borderFill", int(bf)):
            ed.set(ed.el, "borderFillIDRef", str(self.import_borderfill(other, int(bf))))
        return self.add("charPr", ed.result())

    def import_borderfill(self, other: "HeaderStyles", iid: int) -> int:
        xml = other.xml("borderFill", iid)
        xml = re.sub(r"<(\w+:)?imgBrush\b.*?(?:/>|</\1?imgBrush>)", "", xml, flags=re.S)
        return self.add("borderFill", xml)

    def import_tabpr(self, other: "HeaderStyles", iid: int) -> int:
        return self.add("tabPr", other.xml("tabPr", iid))

    def import_parapr(self, other: "HeaderStyles", iid: int) -> int:
        ed = ElemEditor(other.xml("paraPr", iid))
        tab = ed.get(ed.el, "tabPrIDRef")
        if tab is not None and tab.isdigit() and other.has("tabPr", int(tab)):
            ed.set(ed.el, "tabPrIDRef", str(self.import_tabpr(other, int(tab))))
        for hd in ed.nodes("heading"):
            if (ed.get(hd, "type") or "NONE") != "NONE":
                ed.set(hd, "type", "NONE")
                ed.set(hd, "idRef", "0")
                ed.set(hd, "level", "0")
        for b in ed.nodes("border"):
            bf = ed.get(b, "borderFillIDRef")
            if bf is not None and bf.isdigit() and other.has("borderFill", int(bf)):
                ed.set(b, "borderFillIDRef", str(self.import_borderfill(other, int(bf))))
        return self.add("paraPr", ed.result())

    # ── 반영 ──
    def commit(self) -> None:
        if not self.pending:
            return
        self._ensure()
        src = self.src
        splices: List[Splice] = []
        for kind, items in self._pending_items.items():
            if not items:
                continue
            cont = self._containers[kind]
            payload = "".join(x for _, x in items)
            total = len(self._items[kind]) + len(items)
            tag = xmlspan.set_attr(cont.open_tag(src), "itemCnt", str(total))
            if cont.self_closing:
                opened = tag[:-2].rstrip() + ">"
                splices.append(Splice(cont.start, cont.end, opened + payload + f"</{cont.name}>"))
            else:
                splices.append(Splice(cont.start, cont.open_end, tag))
                splices.append(Splice(cont.close_start, cont.close_start, payload))
        for lang, fonts in self._pending_fonts.items():
            if not fonts:
                continue
            ff = self._fontfaces[lang]
            payload = "".join(x for _, _, x in fonts)
            total = len(self._fonts[lang]) + len(fonts)
            tag = xmlspan.set_attr(ff.open_tag(src), "fontCnt", str(total))
            if ff.self_closing:
                opened = tag[:-2].rstrip() + ">"
                splices.append(Splice(ff.start, ff.end, opened + payload + f"</{ff.name}>"))
            else:
                splices.append(Splice(ff.start, ff.open_end, tag))
                splices.append(Splice(ff.close_start, ff.close_start, payload))
        self._pending_items.clear()
        self._pending_fonts.clear()
        self._pending_xml.clear()
        self.doc.set_text(self.path, apply_splices(src, splices), layout_changed=False)
        self._parsed = False
        self._canon.clear()


def _in_default_branch(node: xmlspan.Node) -> bool:
    for a in node.ancestors():
        if a.local == "default":
            return True
        if a.local == "case":
            return False
    return False


def _preferred(ed: ElemEditor, local: str) -> Optional[xmlspan.Node]:
    """hp:case(한컴 실제 값) 쪽을 우선, 없으면 일반/기본 쪽."""
    nodes = ed.nodes(local)
    for n in nodes:
        if any(a.local == "case" for a in n.ancestors()):
            return n
    for n in nodes:
        if not _in_default_branch(n):
            return n
    return nodes[0] if nodes else None
