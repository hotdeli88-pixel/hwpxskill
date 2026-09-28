"""테스트 양식 생성."""
import os

from hwpxskill.core.package import HwpxDocument
from hwpxskill.skeleton import new_document, para, table

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def fixture(name: str) -> str:
    return os.path.join(FIX, name)


def form_doc() -> HwpxDocument:
    body = "".join([
        para(runs=[(2, "{{"), (0, "기관명}} 운영 계획")], para_pr=1),
        para("작성일: {{작성일}}"),
        para("신청인: ____   연락처:    "),
        para("성별 □남 □여, 동의 여부 □동의"),
        table([["성명", "", "소속", ""], ["생년월일", "", "성별", "□남 □여"]], [6000, 12000, 6000, 12000], tbl_id=1001),
        para(""),
        table([["구분", "세부 내용"],
               ["추진 배경", "□ 예시 항목\n ○ 예시 세부 내용\n  - 예시 하위 내용"],
               ["추진 목표", ""]], [8000, 28000], tbl_id=1002),
        para(""),
        table([["연번", "성명", "학년", "비고"], ["", "", "", ""], ["", "", "", ""]], [5000, 10000, 6000, 15000],
              header=True, tbl_id=1003),
        para("{{본문}}"),
        para("일반(  )통, (한자：    )"),
    ])
    return new_document(body, title="테스트 양식")


def reopen(doc: HwpxDocument) -> HwpxDocument:
    return HwpxDocument(doc.to_bytes())
