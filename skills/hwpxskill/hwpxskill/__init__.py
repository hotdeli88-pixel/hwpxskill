"""hwpxskill — HWPX(한글) 양식 채우기·편집 엔진.

원본 서식을 1바이트도 건드리지 않는 부분 교체 방식으로 누름틀·자리표시·표 라벨 칸·명단표를
채우고, 예시 서식을 익혀 여러 단계 내용을 쓰며, 표 스타일 복제·한글 수식·시험지를 지원한다.
"""
__version__ = "2.0.0"

from .core.package import HwpxDocument  # noqa: E402
from .errors import HwpxError  # noqa: E402

__all__ = ["HwpxDocument", "HwpxError", "__version__"]
