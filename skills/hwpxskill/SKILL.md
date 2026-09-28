---
name: hwpxskill
description: 한글(HWP·HWPX) 문서 작업 스킬. 이미 있는 양식(기안문·보고서·계획서·신청서·학교 문서·시험지)을 분석해 들어갈 내용을 쓰고 원본 서식 그대로 채운다. 누름틀·{{키}}·표 라벨 칸·명단표(행 자동 추가)·본문 라벨·체크박스·괄호 빈칸 채우기, 예시가 있는 셀의 서식을 따라 쓰기, 표 스타일만 다른 표에 입히기, 한글 수식 스크립트 넣기·읽기·고치기, 2단 시험지 만들기와 시험지 양식 채우기, 공문서 표기법·개조식 문체 검사, 개인정보 검사·가리기, HWP→HWPX 변환, PDF 렌더와 자동 검수. .hwp·.hwpx 파일을 읽거나 채우거나 고치거나 만들 때, 한글 문서·공문·서식·시험지 이야기가 나오면 사용한다.
---

# hwpxskill — 한글 양식 채우기·편집

원본 서식을 1바이트도 흐트러뜨리지 않고 바뀐 곳만 고쳐 쓰는 Python 엔진(표준 라이브러리만 사용)과 작업 절차다.

## 실행

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/hwpx.py <명령> ...   # Windows: py -3 또는 python
hwpxskill <명령> ...                                    # pip install hwpxskill 로 설치했을 때
```
`${CLAUDE_SKILL_DIR}`는 이 SKILL.md가 있는 폴더다 (Claude Code 밖의 도구에서는 그 경로를 직접 쓴다).

아래에서는 `hwpx <명령>`으로 줄여 쓴다. 처음 쓰는 PC면 `hwpx doctor`로 PDF 렌더(한글 자동화 또는 rhwp)가 되는지 먼저 본다. 안 되면 [references/setup.md](references/setup.md).

## 꼭 지킬 것

1. **원본을 덮어쓰지 않는다.** 결과는 항상 새 파일(`이름_완성.hwpx` 등)로 저장한다. 엔진도 거부한다.
2. **사실은 지어내지 않는다.** 이름·날짜·금액·연락처·문서번호·기관명·수치처럼 사용자만 아는 값은 물어보거나 `○○○`, `0000. 0. 0.`처럼 표시하고 끝에 목록으로 알린다. 서술(추진 배경, 목적, 기대 효과 등)은 Claude가 쓴다.
3. **마크다운을 쓰지 않는다.** `**굵게**`, `#`, `- [ ]` 대신 한글 문서 부호(□ ○ - · ※, 1. 가. 1) 가))와 들여쓰기로 단계를 나타낸다. 서식은 엔진이 양식의 예시·첫 문단에서 가져온다.
4. **수식은 한글 수식 스크립트만** 쓴다 (`{a} over {b}`, `sqrt {x}`). LaTeX(`\frac`)는 오류다. 글 속에는 `<eq>…</eq>`, 따로 한 줄이면 `<eq block>…</eq>`. 문법은 [references/equation.md](references/equation.md).
5. **XML을 직접 고치지 않는다.** 명령으로 안 되는 편집만 [references/api.md](references/api.md)의 Python API로 한다.
6. `.hwp`를 받으면 명령이 알아서 HWPX로 바꿔(원본 옆 `이름.hwpx`) 작업한다.

## 작업 절차 (5단계)

### 1. 분석
```bash
hwpx analyze 양식.hwpx            # 채울 자리 요약 (--outline: 본문·표 내용까지, --json: 기계용)
```
보고서에서 확인할 것: 누름틀 이름과 **앞뒤 글**(`⟨붙임 ▢ 1부.  끝.⟩`이면 값에 "1부. 끝."을 또 넣지 않는다), `{{키}}`, 표 라벨→값 칸, 명단표 머리행, 본문 `라벨:`, □ 체크박스, `(  )` 빈칸, **예시가 채워진 셀**(그 서식을 따라 씀), 기존 수식. 무엇을 채울지 사용자 요청과 맞춰 목록을 만든다.

### 2. 내용 작성
- 값 JSON을 쓴다. 형식과 예는 [references/fill.md](references/fill.md).
- 서술형은 양식 성격(기안문·보고서·가정통신문·계획서)에 맞는 개조식으로 쓴다. 공문서 문체는 [references/gongmun.md](references/gongmun.md).
- 쓴 뒤 검사하고 고친다: `hwpx lint 값.json --munche` (날짜 `2026. 9. 28.`, 시간 `14:00`, 금액, `붙임`·`끝.`, 외래어, `~다` 종결 등).

### 3. 서식
- 여러 줄 값은 줄 앞 부호와 들여쓰기로 단계를 표시하면, 엔진이 같은 셀·표의 예시 문단 서식(부호별 글자·문단 모양)을 익혀 그대로 입힌다. 예시가 없으면 첫 문단 서식에 단계별 내어쓰기만 더한다.
- 표 모양을 다른 표(다른 문서도 가능)와 맞춰야 하면: `hwpx table-style 대상.hwpx --from s0.t0 [--source 견본.hwpx] --to s0.t2 s0.t3` — [references/table-style.md](references/table-style.md).

### 4. 조립
```bash
hwpx fill 양식.hwpx -d 값.json --dry-run        # 어디에 무엇이 들어갈지 미리 보기 (저장 안 함)
hwpx fill 양식.hwpx -d 값.json -o 결과.hwpx      # 저장 + 자동 검수
```
미리 보기에서 `건너뜀`, `안 쓰인 키`, 경고를 모두 해결한 뒤 저장한다. 시험지는 `hwpx exam -d 문항.json [-t 양식.hwpx] -o 시험지.hwpx` — [references/exam.md](references/exam.md). 기존 수식 고치기는 `hwpx equation list/set`.

### 5. 검수
`fill`·`exam`은 저장 뒤 자동으로 검수한다(따로 할 때는 `hwpx check 결과.hwpx`): 구조(ZIP·XML·스타일 참조·개수), 남은 `{{}}`·빈 누름틀, 수식 문법, 개인정보, 표기법, 그리고 PDF 렌더.
- **PDF를 직접 열어 페이지를 본다** (Claude Code는 Read 도구로 PDF를 볼 수 있다). 글자 넘침, 표 깨짐, 빈 칸, 수식 모양, 쪽 넘김을 확인하고 문제가 있으면 값을 고쳐 4단계를 다시 한다.
- 사용자에게 보고한다: 결과 파일(HWPX·PDF) 경로, 채운 항목 수, **확인이 필요한 값(`○○○` 등) 목록**, 남은 빈칸, 표기법·개인정보 경고(개인정보는 경고만 — 요청하면 `hwpx privacy redact`로 가린 사본). 자세한 기준은 [references/check.md](references/check.md).
- Claude Code에서 문서가 길면 PDF 페이지 확인을 보조 에이전트에게 나눠 맡겨도 된다(선택).

## 명령 요약

| 명령 | 하는 일 |
|---|---|
| `analyze 파일 [--outline] [--json]` | 채울 자리·예시 셀·표·수식 목록 |
| `text 파일` | 문단·표 셀을 주소(`s0.p3`, `s0.t1.r2.c1`)와 함께 보기 |
| `fill 파일 -d 값.json [-o 출력] [--dry-run] [--strict]` | 양식 채우기 (+자동 검수) |
| `table-style 파일 --from 표 [--source 문서] --to 표…` | 표 스타일만 입히기 |
| `equation list 파일` / `check "스크립트"` / `set 파일 --index N 또는 --find 글 --script 새것` | 수식 보기·검사·바꾸기 |
| `exam -d 문항.json [-t 양식] -o 출력` | 시험지 만들기·양식 채우기 |
| `lint 파일 또는 값.json [--munche]` | 공문서 표기법(22개)·개조식 문체(12개) 검사 |
| `privacy scan 파일` / `privacy redact 파일 [-o 출력]` | 개인정보 경고 / 가린 사본 |
| `validate 파일` / `check 파일` | 구조 검사 / 전체 검수(+PDF) |
| `render 파일 [-o 출력.pdf]` | PDF 만들기 (Windows 한글 → 없으면 rhwp) |
| `convert 파일.hwp [--to hwpx/hwp/pdf]` | 형식 변환 |
| `doctor` | 실행 환경 점검 |

주소: `s0` 구역, `p5` 문단, `t1` 표(중첩 표 포함 문서 순서), `r2.c1` 행·열(0부터).

## 참고 문서

- [references/fill.md](references/fill.md) — 값 JSON, 자리 종류별 채우기 규칙, 여러 줄 서식, 명단표
- [references/equation.md](references/equation.md) — 한글 수식 스크립트 문법 요약 (LaTeX 대응표)
- [references/exam.md](references/exam.md) — 시험지 문항 JSON, 양식 모드, 보기 배치
- [references/table-style.md](references/table-style.md) — 표 스타일 복제의 역할 매핑
- [references/gongmun.md](references/gongmun.md) — 공문서 표기법·개조식 문체 규칙과 문서 종류별 틀
- [references/check.md](references/check.md) — 검수 항목, PDF 확인 요령, 보고 틀, 개인정보
- [references/setup.md](references/setup.md) — Windows(한글 자동화)·Mac(rhwp) 설치, 다른 에이전트 도구
- [references/api.md](references/api.md) — 명령으로 안 되는 편집용 Python API

## 문제가 생기면

| 증상 | 해결 |
|---|---|
| `HWP(바이너리) 파일입니다` | 변환 엔진이 없음 → `hwpx doctor`, [setup.md](references/setup.md) |
| `건너뜀: … 겹침` | 같은 자리를 두 키가 채움 → 하나만 남기거나 `cells` 주소로 지정 |
| `안 쓰인 키` | 이름이 양식과 다름 → `analyze`의 이름을 그대로 쓰거나 `cells` 주소 사용 |
| 명단표 행이 안 늘어남 | 세로 병합된 행 → 경고에 나온 대로 앞 행까지만 채워짐, 사용자에게 알림 |
| 수식 오류 | `hwpx equation check "스크립트"`로 고친 뒤 다시 |
| PDF 렌더 건너뜀 | 렌더 엔진 없음 → HWPX만 전달하고 한글에서 열어 확인하도록 안내 |
| 파일이 열려 있어 저장 실패 | 자동으로 `_v1` 같은 새 이름으로 저장됨 — 보고할 때 실제 경로를 쓴다 |
