# 테스트 픽스처

| 파일 | 출처 |
|---|---|
| `gian_general.hwpx`, `gian_simple.hwpx`, `gian_general_values.json` | [kordoc](https://github.com/chrisryugj/kordoc) `templates/` (MIT, © chrisryugj) — 행정업무운영 편람 별지 기안문 서식 |

그 밖의 테스트 양식은 `tests/helpers.py`가 실행 때 만든다. 개인정보가 들어간 실제 문서는 올리지 않는다.
실제 한글 저장본으로 더 넓게 시험하려면 `HWPXSKILL_SAMPLES=<hwpx 폴더>` 를 지정하고 `pytest -m samples` 를 실행한다
(예: [rhwp](https://github.com/edwardkim/rhwp) `samples/hwpx`).
