"""HWPX 문서 패키지: 파트 읽기·편집·저장."""
from __future__ import annotations

import os
import posixpath
import re
from typing import Dict, Iterable, List, Optional, Set, Tuple

from ..errors import HwpxError
from . import xmlspan
from .splice import Splice, apply_splices
from .zipio import ZipArchive

MIMETYPE = "application/hwp+zip"
NS_PARAGRAPH = "http://www.hancom.co.kr/hwpml/2011/paragraph"
NS_SECTION = "http://www.hancom.co.kr/hwpml/2011/section"
NS_HEAD = "http://www.hancom.co.kr/hwpml/2011/head"
NS_CORE = "http://www.hancom.co.kr/hwpml/2011/core"
STANDARD_PREFIX = {NS_PARAGRAPH: "hp", NS_SECTION: "hs", NS_HEAD: "hh", NS_CORE: "hc"}

_LINESEG_RE = re.compile(r"<(\w+:)?linesegarray\b[^>]*?(?:/>|>.*?</\1?linesegarray>)", re.S)


class HwpxDocument:
    """HWPX 파일 하나. 파트는 문자열로 다루고, 바뀐 파트만 저장 시 다시 압축한다."""

    def __init__(self, data: bytes, path: Optional[str] = None):
        self.path = path
        if data[:4] == b"\xd0\xcf\x11\xe0":
            raise HwpxError("HWP(바이너리) 파일입니다. `convert`로 HWPX로 바꾸거나 명령에 .hwp를 그대로 주면 자동으로 바꿉니다")
        self.archive = ZipArchive.from_bytes(data)
        names = self.archive.names()
        if "mimetype" not in names:
            raise HwpxError("HWPX 파일이 아닙니다 (mimetype 없음)")
        mt = self.archive.read("mimetype").decode("ascii", "replace").strip()
        if mt != MIMETYPE:
            raise HwpxError(f"HWPX 파일이 아닙니다 (mimetype={mt!r})")
        if "META-INF/manifest.xml" in names and b"encryption-data" in self.archive.read("META-INF/manifest.xml"):
            raise HwpxError("암호가 걸린 HWPX입니다. 한글에서 문서 암호를 풀고 다시 저장한 뒤 사용해 주세요")
        self._text: Dict[str, str] = {}
        self._tree: Dict[str, xmlspan.Node] = {}
        self._dirty: Set[str] = set()
        self._layout_dirty: Set[str] = set()
        self._added: Dict[str, Tuple[bytes, bool]] = {}
        self._binary: Dict[str, bytes] = {}
        self.hpf_path = self._find_rootfile()
        self.section_paths, self.header_path = self._read_spine()
        self._header = None

    # ── 열기 ──
    @classmethod
    def open(cls, path: str) -> "HwpxDocument":
        if not os.path.exists(path):
            raise HwpxError(f"파일이 없습니다: {path}")
        if path.lower().endswith(".hwp") and not path.lower().endswith(".hwpx"):
            raise HwpxError("HWP(바이너리) 파일입니다. `convert`로 HWPX로 바꾸거나 명령에 .hwp를 그대로 주면 자동으로 바꿉니다")
        with open(path, "rb") as f:
            data = f.read()
        return cls(data, path)

    def _find_rootfile(self) -> str:
        if "META-INF/container.xml" in self.archive.names():
            src = self.archive.read("META-INF/container.xml").decode("utf-8", "replace")
            for m in re.finditer(r"<[\w:]*rootfile\b[^>]*>", src):
                tag = m.group(0)
                href = xmlspan.get_attr(tag, "full-path") or ""
                mt = xmlspan.get_attr(tag, "media-type") or ""
                if href.endswith(".hpf") or "hwpml-package" in mt:
                    return href
        return "Contents/content.hpf"

    def _resolve(self, href: str) -> str:
        if href in self.archive.names():
            return href
        base = posixpath.dirname(self.hpf_path)
        joined = posixpath.normpath(posixpath.join(base, href))
        return joined

    def _read_spine(self) -> Tuple[List[str], str]:
        names = set(self.archive.names())
        sections: List[str] = []
        header = "Contents/header.xml"
        if self.hpf_path in names:
            src = self.archive.read(self.hpf_path).decode("utf-8", "replace")
            items: Dict[str, str] = {}
            for m in re.finditer(r"<[\w:]*item\b[^>]*>", src):
                tag = m.group(0)
                iid = xmlspan.get_attr(tag, "id")
                href = xmlspan.get_attr(tag, "href")
                if iid and href:
                    items[iid] = self._resolve(href)
            for iid, p in items.items():
                if re.search(r"header\d*\.xml$", p):
                    header = p
                    break
            for m in re.finditer(r"<[\w:]*itemref\b[^>]*>", src):
                ref = xmlspan.get_attr(m.group(0), "idref")
                p = items.get(ref or "")
                if p and re.search(r"section\d+\.xml$", p) and p in names:
                    sections.append(p)
        if not sections:
            sections = sorted((n for n in names if re.fullmatch(r"Contents/section\d+\.xml", n)),
                              key=lambda n: int(re.search(r"(\d+)\.xml$", n).group(1)))
        if not sections:
            raise HwpxError("본문 섹션(section*.xml)이 없습니다")
        return sections, header

    # ── 파트 접근 ──
    def has(self, name: str) -> bool:
        return name in self._text or name in self._added or name in self.archive.names()

    def text(self, name: str) -> str:
        if name not in self._text:
            if name in self._added:
                raw = self._added[name][0]
            else:
                raw = self.archive.read(name)
            if raw.startswith(b"\xef\xbb\xbf"):
                raw = raw[3:]
            self._text[name] = raw.decode("utf-8")
        return self._text[name]

    def tree(self, name: str) -> xmlspan.Node:
        if name not in self._tree:
            self._tree[name] = xmlspan.parse(self.text(name))
        return self._tree[name]

    def set_text(self, name: str, new: str, layout_changed: bool = True) -> None:
        if self._text.get(name) == new:
            return
        self._text[name] = new
        self._tree.pop(name, None)
        self._dirty.add(name)
        if layout_changed and name in self.section_paths:
            self._layout_dirty.add(name)
        if name == self.header_path and self._header is not None:
            self._header.invalidate()

    def apply(self, name: str, splices: Iterable[Splice], layout_changed: bool = True) -> None:
        sp = list(splices)
        if not sp:
            return
        self.set_text(name, apply_splices(self.text(name), sp), layout_changed)

    def add_part(self, name: str, data: bytes, compress: bool = True) -> None:
        self._added[name] = (data, compress)

    def set_binary(self, name: str, data: bytes) -> None:
        """이미지 같은 바이너리 파트를 교체한다."""
        self._binary[name] = data

    @property
    def header(self):
        if self._header is None:
            from .header import HeaderStyles
            self._header = HeaderStyles(self)
        return self._header

    @property
    def modified(self) -> bool:
        return bool(self._dirty or self._added or self._binary) or (
            self._header is not None and self._header.pending)

    def prefix(self, part: str, uri: str) -> str:
        pf = xmlspan.namespace_prefixes(self.text(part), self.tree(part))
        return pf.get(uri, STANDARD_PREFIX.get(uri, ""))

    # ── 저장 ──
    def to_bytes(self, drop_layout_cache: bool = True, refresh_preview: bool = True) -> bytes:
        if self._header is not None:
            self._header.commit()
        if refresh_preview and self._layout_dirty and "Preview/PrvText.txt" in self.archive.names() \
                and "Preview/PrvText.txt" not in self._dirty:
            self._text["Preview/PrvText.txt"] = preview_text(self)
            self._dirty.add("Preview/PrvText.txt")
        if drop_layout_cache:
            for name in list(self._layout_dirty):
                cleaned = _LINESEG_RE.sub("", self.text(name))
                self._text[name] = cleaned
                self._tree.pop(name, None)
        replaced = {n: self._text[n].encode("utf-8") for n in self._dirty if n not in self._added}
        replaced.update(self._binary)
        added = [(n, self._text[n].encode("utf-8") if n in self._dirty else d, c)
                 for n, (d, c) in self._added.items()]
        return self.archive.rebuild(replaced, added)

    def save(self, out_path: str, overwrite_source: bool = False) -> str:
        if self.path and not overwrite_source and os.path.abspath(out_path) == os.path.abspath(self.path):
            raise HwpxError("원본 파일은 덮어쓰지 않습니다. 다른 출력 경로를 지정해 주세요")
        data = self.to_bytes()
        d = os.path.dirname(os.path.abspath(out_path))
        os.makedirs(d, exist_ok=True)
        return write_with_lock_fallback(out_path, data)


def preview_text(doc: "HwpxDocument", limit: int = 1500) -> str:
    """Preview/PrvText.txt 형식(표 칸은 <…>)의 미리보기 글."""
    from .model import Section
    from .text import ParaText
    out: List[str] = []
    size = 0
    for si in range(len(doc.section_paths)):
        sec = Section(doc, si)
        for p in sec.paragraphs():
            line = ParaText(sec.src, p).text.replace("\t", " ")
            parts = [line] if line.strip() else []
            for tbl in p.iter("tbl"):
                if tbl.ancestor("tbl") is not None:
                    continue
                t = sec.table_of(tbl)
                if t is None:
                    continue
                rows: Dict[int, List[str]] = {}
                for c in t.cells(sec.src):
                    rows.setdefault(c.tr_index, []).append("<" + c.text(sec.src).replace("\n", " ") + ">")
                parts.extend("".join(r) for _, r in sorted(rows.items()))
            for x in parts:
                out.append(x)
                size += len(x) + 2
            if size > limit:
                return "\r\n".join(out)[:limit]
    return "\r\n".join(out)


def write_with_lock_fallback(path: str, data: bytes, max_fallback: int = 20) -> str:
    """한글에서 열려 있어 잠긴 파일이면 `_v1`, `_v2`… 이름으로 저장한다."""
    stem, ext = os.path.splitext(path)
    for i in range(max_fallback + 1):
        target = path if i == 0 else f"{stem}_v{i}{ext}"
        try:
            with open(target, "wb") as f:
                f.write(data)
            return target
        except PermissionError:
            continue
    raise HwpxError(f"파일을 저장할 수 없습니다 (잠김): {path}")
