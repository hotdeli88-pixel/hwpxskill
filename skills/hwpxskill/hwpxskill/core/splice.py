"""원문 문자열 부분 교체(splice)."""
from __future__ import annotations

from typing import Iterable, List, NamedTuple

from ..errors import HwpxError


class Splice(NamedTuple):
    start: int
    end: int
    text: str


def apply_splices(src: str, splices: Iterable[Splice]) -> str:
    """겹치지 않는 교체 목록을 한 번에 적용한다. 같은 위치 삽입은 추가 순서를 지킨다."""
    items = sorted(enumerate(splices), key=lambda x: (x[1].start, x[1].end, x[0]))
    out: List[str] = []
    pos = 0
    for _, sp in items:
        if sp.start < pos or sp.end < sp.start:
            raise HwpxError(f"편집 범위가 겹칩니다 ({sp.start}:{sp.end}, 이전 끝 {pos})")
        out.append(src[pos:sp.start])
        out.append(sp.text)
        pos = sp.end
    out.append(src[pos:])
    return "".join(out)
