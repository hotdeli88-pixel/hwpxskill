# Python API (명령으로 안 되는 편집)

먼저 명령(`fill`의 `cells`·`rows`, `table-style`, `equation set`)으로 되는지 본다. 안 될 때만 쓴다.

```python
import sys; sys.path.insert(0, "<스킬 폴더>")        # pip로 설치했으면 필요 없음
from hwpxskill import HwpxDocument
from hwpxskill.core.model import Section
from hwpxskill.core.text import ParaText, inline_xml
from hwpxskill.core.splice import Splice
```

## 원칙

- XML을 파싱해 다시 쓰지 않는다. **원문 문자열에서 바꿀 구간(`Splice(start, end, 새글)`)을 모아 한 번에 적용**한다 (`doc.apply(파트, splices)`). 나머지 바이트는 그대로 남는다.
- 한 파트에 대한 splice들은 **같은 원문 기준 위치**로 만들고 한 번에 적용한다. 적용한 뒤에는 위치가 바뀌므로 `Section`을 다시 만든다.
- 글자는 `xmlspan.escape_text()` / `inline_xml()`로 넣는다 (`&`, `<` 처리, `\t`는 탭).
- 새 글자·문단 모양이 필요하면 `doc.header.derive_charpr(기준id, bold=True, …)`, `derive_parapr(기준id, left=…, intent=…, align=…)` — 같은 정의가 있으면 그 번호를 다시 쓴다. 글꼴은 이름이 아니라 번호로 연결된다 (엔진이 처리).
- 저장은 `doc.save("새이름.hwpx")` (원본 경로면 거부). 저장하면 바뀐 구역의 줄 배치 캐시를 지우고 미리보기 글을 새로 만든다.

## 주요 객체

| 객체 | 쓰임 |
|---|---|
| `HwpxDocument.open(path)` | 열기. `section_paths`, `header_path`, `text(파트)`, `tree(파트)`, `apply(파트, splices)`, `set_text`, `save` |
| `Section(doc, i)` | 구역. `src`(원문), `paragraphs()`(본문 문단), `tables()`(중첩 포함, 문서 순서), `table(i)`, `paragraph_address(p)`, `hp`(접두어) |
| `Table` | `id`(`s0.t1`), `cells(src)`, `cell(src, 행, 열)`, `row_cells(src, tr번호)`, `rows()`, `grid_text(src)` |
| `Cell` | `address`, `row`, `col`, `rowspan`, `colspan`, `paragraphs()`, `text(src)`, `tc`(노드) |
| `ParaText(src, p)` | 문단 글. `text`, `replace(시작, 끝, xml) → [Splice]`(여러 글자 모양에 걸쳐도 됨), `run_at(위치)` |
| `xmlspan.Node` | `start`/`end`(원문 위치), `open_tag(src)`, `get(src, 속성)`, `find(이름)`, `iter(이름)`, `inner(src)` |
| `doc.header` | 글자·문단·테두리 모양: `charpr(id)`, `parapr(id)`, `borderfill(id)`, `derive_charpr`, `derive_parapr`, `add(kind, xml)` |

기능 함수: `hwpxskill.fill.fill_document(doc, data)`, `analyze.analyze(doc)`, `tablestyle.apply_table_style(doc, [대상], 원본, source_doc=)`, `equation.list_equations/replace_equation`, `exam.build_exam(data, template, output)`, `validate.validate(doc)`, `lint.lint_document(doc)`, `privacy.scan_document/redact_document`, `render.render_pdf/convert/ensure_hwpx`.

## 예: 문서 전체에서 낱말 바꾸기 (서식 유지)

```python
doc = HwpxDocument.open("보고서.hwpx")
for i in range(len(doc.section_paths)):
    sec = Section(doc, i)
    splices = []
    for p in sec.iter_paragraphs():            # 표 셀·글상자 안 문단까지
        pt = ParaText(sec.src, p)
        start = 0
        while (k := pt.text.find("2025학년도", start)) >= 0:
            splices += pt.replace(k, k + len("2025학년도"), inline_xml("2026학년도"))
            start = k + 1
    if splices:
        doc.apply(sec.path, splices)
doc.save("보고서_2026.hwpx")
```

`ParaText`는 그 문단의 글자만 담으므로(셀 안 문단은 따로 돈다) 표 안팎을 함께 바꿔도 splice가 겹치지 않는다. 바꾼 뒤 `hwpx check`로 검수한다.
