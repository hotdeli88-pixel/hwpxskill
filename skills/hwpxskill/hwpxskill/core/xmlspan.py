"""오프셋 보존 XML 파서.

HWPX 파트(XML)를 DOM으로 다시 직렬화하지 않고 편집하기 위해, 각 요소의 원문 위치
(여는 태그 시작/끝, 닫는 태그 시작/끝)만 기록한 가벼운 트리를 만든다.
편집은 이 위치를 이용한 문자열 부분 교체(splice)로만 한다.
"""
from __future__ import annotations

import re
from typing import Dict, Iterator, List, Optional

from ..errors import HwpxError

_TOKEN_RE = re.compile(
    r"<!--.*?-->"
    r"|<!\[CDATA\[.*?\]\]>"
    r"|<\?.*?\?>"
    r"|<!DOCTYPE[^>]*>"
    r"|<(/?)([A-Za-z_][\w:.\-]*)((?:\s+[^\s=/>]+\s*=\s*(?:\"[^\"]*\"|'[^']*'))*)\s*(/?)>",
    re.S,
)
_ATTR_RE = re.compile(r"([^\s=/>]+)\s*=\s*(?:\"([^\"]*)\"|'([^']*)')")
_ENTITY_RE = re.compile(r"&(#x[0-9A-Fa-f]+|#\d+|[A-Za-z]+);")
_NAMED = {"amp": "&", "lt": "<", "gt": ">", "quot": '"', "apos": "'"}
# XML 1.0에서 허용되지 않는 제어 문자 (탭·줄바꿈·CR 제외) — 한글이 파일을 열지 못한다
_ILLEGAL_CTRL_RE = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f￾￿]")


class Node:
    """원문 위치만 가진 XML 요소."""

    __slots__ = ("name", "start", "open_end", "close_start", "end", "parent", "children", "_attrs")

    def __init__(self, name: str, start: int, open_end: int, parent: Optional["Node"]):
        self.name = name
        self.start = start
        self.open_end = open_end
        self.close_start = open_end
        self.end = open_end
        self.parent = parent
        self.children: List[Node] = []
        self._attrs: Optional[Dict[str, str]] = None

    # ── 이름 ──
    @property
    def local(self) -> str:
        i = self.name.rfind(":")
        return self.name[i + 1:] if i >= 0 else self.name

    @property
    def prefix(self) -> str:
        i = self.name.find(":")
        return self.name[:i] if i >= 0 else ""

    @property
    def self_closing(self) -> bool:
        return self.close_start == self.open_end == self.end and self.name != "#document"

    # ── 원문 조각 ──
    def outer(self, src: str) -> str:
        return src[self.start:self.end]

    def inner(self, src: str) -> str:
        return src[self.open_end:self.close_start]

    def open_tag(self, src: str) -> str:
        return src[self.start:self.open_end]

    def attrs(self, src: str) -> Dict[str, str]:
        if self._attrs is None:
            tag = src[self.start:self.open_end]
            self._attrs = {m.group(1): unescape(m.group(2) if m.group(2) is not None else m.group(3))
                           for m in _ATTR_RE.finditer(tag, len(self.name) + 1)}
        return self._attrs

    def get(self, src: str, key: str, default: Optional[str] = None) -> Optional[str]:
        return self.attrs(src).get(key, default)

    # ── 탐색 ──
    def find(self, local: str) -> Optional["Node"]:
        for c in self.children:
            if c.local == local:
                return c
        return None

    def findall(self, local: str) -> List["Node"]:
        return [c for c in self.children if c.local == local]

    def iter(self, local: Optional[str] = None) -> Iterator["Node"]:
        """자기 자신을 뺀 모든 자손(문서 순서)."""
        stack = list(reversed(self.children))
        while stack:
            n = stack.pop()
            if local is None or n.local == local:
                yield n
            if n.children:
                stack.extend(reversed(n.children))

    def iter_until(self, local: str, stop: frozenset) -> Iterator["Node"]:
        """`stop`에 든 요소 안으로는 내려가지 않는 자손 탐색 (중첩 표 경계 등)."""
        stack = list(reversed(self.children))
        while stack:
            n = stack.pop()
            if n.local == local:
                yield n
            if n.children and n.local not in stop:
                stack.extend(reversed(n.children))

    def ancestors(self) -> Iterator["Node"]:
        n = self.parent
        while n is not None and n.name != "#document":
            yield n
            n = n.parent

    def ancestor(self, local: str) -> Optional["Node"]:
        for a in self.ancestors():
            if a.local == local:
                return a
        return None

    def index_in_parent(self) -> int:
        return self.parent.children.index(self) if self.parent else -1

    def __repr__(self) -> str:  # pragma: no cover - 디버깅용
        return f"<Node {self.name} {self.start}:{self.end}>"


def parse(src: str) -> Node:
    """XML 문자열을 위치 트리로 파싱한다. 루트는 가상 노드 `#document`."""
    root = Node("#document", 0, 0, None)
    stack: List[Node] = [root]
    for m in _TOKEN_RE.finditer(src):
        name = m.group(2)
        if name is None:
            continue
        if m.group(1):
            if len(stack) == 1:
                raise HwpxError(f"XML 구조 오류: 짝 없는 닫는 태그 </{name}> (위치 {m.start()})")
            node = stack.pop()
            if node.name != name:
                raise HwpxError(f"XML 구조 오류: <{node.name}> 를 </{name}> 로 닫음 (위치 {m.start()})")
            node.close_start = m.start()
            node.end = m.end()
        else:
            node = Node(name, m.start(), m.end(), stack[-1])
            stack[-1].children.append(node)
            if m.group(4):
                node.close_start = node.end = m.end()
            else:
                stack.append(node)
    if len(stack) != 1:
        raise HwpxError(f"XML 구조 오류: 닫히지 않은 요소 <{stack[-1].name}>")
    root.close_start = root.end = len(src)
    return root


def document_element(root: Node) -> Node:
    for c in root.children:
        return c
    raise HwpxError("XML 루트 요소가 없습니다")


# ── 문자열 이스케이프 ──

def unescape(s: str) -> str:
    if "&" not in s:
        return s

    def rep(m: "re.Match[str]") -> str:
        g = m.group(1)
        if g[0] == "#":
            try:
                return chr(int(g[2:], 16) if g[1] in "xX" else int(g[1:]))
            except ValueError:
                return m.group(0)
        return _NAMED.get(g, m.group(0))

    return _ENTITY_RE.sub(rep, s)


def escape_text(s: str) -> str:
    s = _ILLEGAL_CTRL_RE.sub("", s)
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def escape_attr(s: str) -> str:
    return escape_text(s).replace('"', "&quot;")


# ── 여는 태그 속성 편집 ──

def set_attr(tag: str, key: str, value: str) -> str:
    """여는 태그 문자열의 속성 하나를 바꾸거나 추가한 새 태그를 돌려준다."""
    pat = re.compile(r"(\s" + re.escape(key) + r"\s*=\s*)(\"[^\"]*\"|'[^']*')")
    m = pat.search(tag)
    val = escape_attr(value)
    if m:
        return tag[:m.start(2)] + f'"{val}"' + tag[m.end(2):]
    end = len(tag) - 2 if tag.endswith("/>") else len(tag) - 1
    while end > 0 and tag[end - 1].isspace():
        end -= 1
    return tag[:end] + f' {key}="{val}"' + tag[end:]


def remove_attr(tag: str, key: str) -> str:
    return re.sub(r"\s" + re.escape(key) + r"\s*=\s*(\"[^\"]*\"|'[^']*')", "", tag, count=1)


def get_attr(tag: str, key: str) -> Optional[str]:
    m = re.search(r"\s" + re.escape(key) + r"\s*=\s*(?:\"([^\"]*)\"|'([^']*)')", tag)
    if not m:
        return None
    return unescape(m.group(1) if m.group(1) is not None else m.group(2))


def namespace_prefixes(src: str, root: Node) -> Dict[str, str]:
    """루트 요소에 선언된 네임스페이스 URI → 접두어."""
    el = document_element(root)
    out: Dict[str, str] = {}
    for k, v in el.attrs(src).items():
        if k.startswith("xmlns:"):
            out[v] = k[6:]
    return out
