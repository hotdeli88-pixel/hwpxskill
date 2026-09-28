"""요소 하나(원문 XML 조각)를 부분 교체로 고치는 도구."""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from . import xmlspan
from .splice import Splice, apply_splices


class ElemEditor:
    """XML 조각의 속성·자식을 고쳐 새 문자열을 만든다. 손대지 않은 부분은 원문 그대로다."""

    def __init__(self, xml: str):
        self.src = xml
        self.root = xmlspan.parse(xml)
        self.el = xmlspan.document_element(self.root)
        self._attrs: Dict[int, Tuple[xmlspan.Node, Dict[str, Optional[str]]]] = {}
        self._splices: List[Splice] = []

    def nodes(self, local: str) -> List[xmlspan.Node]:
        """루트를 포함해 이름이 `local`인 모든 요소."""
        out = [self.el] if self.el.local == local else []
        out.extend(self.el.iter(local))
        return out

    def first(self, local: str) -> Optional[xmlspan.Node]:
        n = self.nodes(local)
        return n[0] if n else None

    def get(self, node: xmlspan.Node, key: str) -> Optional[str]:
        pend = self._attrs.get(id(node))
        if pend and key in pend[1]:
            return pend[1][key]
        return node.get(self.src, key)

    def set(self, node: xmlspan.Node, key: str, value: Optional[str]) -> None:
        self._attrs.setdefault(id(node), (node, {}))[1][key] = value

    def remove(self, node: xmlspan.Node) -> None:
        self._splices.append(Splice(node.start, node.end, ""))

    def insert_before(self, node: xmlspan.Node, xml: str) -> None:
        self._splices.append(Splice(node.start, node.start, xml))

    def append_child(self, parent: xmlspan.Node, xml: str) -> None:
        if parent.self_closing:
            tag = parent.open_tag(self.src)
            opened = tag[:-2].rstrip() + ">"
            self._splices.append(Splice(parent.start, parent.end, opened + xml + f"</{parent.name}>"))
        else:
            self._splices.append(Splice(parent.close_start, parent.close_start, xml))

    def result(self) -> str:
        splices = list(self._splices)
        for node, changes in self._attrs.values():
            tag = node.open_tag(self.src)
            for k, v in changes.items():
                tag = xmlspan.remove_attr(tag, k) if v is None else xmlspan.set_attr(tag, k, v)
            splices.append(Splice(node.start, node.open_end, tag))
        return apply_splices(self.src, splices)


def canonical(xml: str) -> str:
    """중복 판정용 정규형: 루트 id 속성 제거 + 태그 사이 공백 정리."""
    import re
    head_end = xml.find(">")
    head = xmlspan.remove_attr(xml[:head_end + 1], "id")
    body = xml[head_end + 1:]
    return re.sub(r">\s+<", "><", head + body).strip()
