# hwpxskill

한글(HWP·HWPX) 양식에 들어갈 내용을 AI 에이전트가 쓰고, **원본 서식 그대로** 채워 넣는 스킬과 엔진입니다.
Claude Code 스킬(플러그인)로, 다른 에이전트 도구의 스킬 폴더로, 또는 `pip` 명령줄 도구로 씁니다.

- **양식 채우기** — 누름틀, `{{키}}`, 표의 라벨 옆 칸, 명단표(모자라면 마지막 행 서식째 행 추가), 본문 `라벨:`, 체크박스(`성별 □남 □여`), 괄호 빈칸
- **서식을 갖춘 내용** — 셀에 예시로 쓰인 문단의 부호별(□ ○ -) 글자·문단 모양을 익혀 새 내용에 입히고, 예시가 없으면 첫 문단 서식에 단계별 내어쓰기
- **표 스타일 복제** — 다른 표(다른 문서도)의 테두리·배경·글자 모양만 역할(머리행·라벨 열·본문·합계행) 기준으로 입히기
- **한글 수식** — 수식 스크립트로 글 속·한 줄 수식 넣기, 기존 수식 읽기·찾아 바꾸기, 저장 전 문법 검사
- **시험지** — 2단 시험지 새로 만들기 또는 학교 양식 채우기, 문항 번호·배점·<보기> 상자, 보기 ①~⑤ 자동 배치
- **검사** — 공문서 표기법 22개·개조식 문체 12개, 개인정보(경고 + 가린 사본), 구조 검증, PDF 렌더로 눈 검수
- **HWP 입력** — `.hwp`는 자동으로 HWPX로 바꿔 작업 (Windows 한글 자동화 / Mac·Linux rhwp)

원본 XML을 다시 조립하지 않고 **바뀐 부분만 원문에서 교체**하며, 손대지 않은 파일은 1바이트도 바뀌지 않습니다 (공개 샘플 393개로 확인). 엔진은 Python 3.9+ 표준 라이브러리만 씁니다.

## 설치

**Claude Code 플러그인**
```
/plugin marketplace add hotdeli88-pixel/hwpxskill
/plugin install hwpxskill@hwpxskill
```

**스킬 폴더 복사** (Claude Code 개인 스킬, Antigravity 등) — `skills/hwpxskill` 폴더를 `~/.claude/skills/` 또는 도구의 스킬 폴더로 복사.

**pip**
```bash
pip install "git+https://github.com/hotdeli88-pixel/hwpxskill"   # PyPI 배포 전
hwpxskill doctor
```

PDF 렌더·HWP 변환: Windows는 한글 2022 이상 + `pywin32`, Mac·Linux는 [rhwp](https://github.com/edwardkim/rhwp) (`skills/hwpxskill/scripts/install_rhwp.sh`). 자세한 설정은 [references/setup.md](skills/hwpxskill/references/setup.md).

## 사용

에이전트에게 "이 양식에 ○○ 내용을 채워 줘"처럼 요청하면 [SKILL.md](skills/hwpxskill/SKILL.md)의 5단계(분석 → 내용 작성 → 서식 → 조립 → 검수)를 따릅니다. 사람이 직접 쓸 때:

```bash
hwpx() { python3 skills/hwpxskill/scripts/hwpx.py "$@"; }    # 또는 pip 설치 후 hwpxskill

hwpx analyze 양식.hwpx                          # 채울 자리·예시 셀·수식 목록
hwpx fill 양식.hwpx -d 값.json --dry-run        # 미리 보기
hwpx fill 양식.hwpx -d 값.json -o 완성.hwpx      # 저장 + 검수(구조·개인정보·표기법·PDF)
hwpx table-style 문서.hwpx --from s0.t0 --to s0.t2 -o 결과.hwpx
hwpx exam -d 문항.json -o 시험지.hwpx
hwpx equation list 문서.hwpx
hwpx lint 값.json --munche
hwpx privacy redact 완성.hwpx -o 완성_가림.hwpx
```

값 JSON 예:
```json
{
  "values": {"제목": "2026학년도 디지털 교육 운영 계획", "작성일": {"value": "20260928", "format": "date:yyyy. m. d."},
             "성별": "남", "추진 배경": "□ 교육 환경 변화\n ○ 학령인구 감소\n  - 2025년 대비 3.2% 감소"},
  "rows": {"s0.t2": [{"성명": "홍길동", "학년": "3"}, {"성명": "김철수", "학년": "2"}]}
}
```

| 문서 | 내용 |
|---|---|
| [SKILL.md](skills/hwpxskill/SKILL.md) | 작업 절차와 명령 요약 |
| [fill.md](skills/hwpxskill/references/fill.md) | 값 JSON, 자리별 규칙, 여러 줄 서식 |
| [equation.md](skills/hwpxskill/references/equation.md) | 한글 수식 스크립트 요약 |
| [exam.md](skills/hwpxskill/references/exam.md) | 시험지 문항 JSON |
| [table-style.md](skills/hwpxskill/references/table-style.md) | 표 스타일 복제 |
| [gongmun.md](skills/hwpxskill/references/gongmun.md) | 공문서 표기법·개조식 문체 |
| [check.md](skills/hwpxskill/references/check.md) | 검수·보고 |
| [api.md](skills/hwpxskill/references/api.md) | Python API |
| [docs/SPEC.md](docs/SPEC.md) | 요구사항 명세 |

## 구조

```
skills/hwpxskill/
  SKILL.md, references/        에이전트용 절차·참고 문서
  scripts/hwpx.py              설치 없이 실행하는 입구
  hwpxskill/                   엔진 (pip 패키지)
    core/                      위치 보존 XML 파서, splice, ZIP 보존 입출력, header 스타일 레지스트리
    analyze.py forms.py        양식 분석 (kordoc 라벨 규칙)
    fill.py content.py         채우기, 예시 서식 학습·내어쓰기
    tablestyle.py tables.py    표 스타일 복제, 행 추가
    equation.py exam.py        수식, 시험지
    lint.py privacy.py         표기법·문체, 개인정보
    validate.py render.py      구조 검증, PDF·변환 (한글 COM / rhwp)
tests/                         pytest (공개 픽스처만)
```

## 개발

```bash
pip install -e ".[dev]"
pytest                                                      # 단위·명령줄 테스트
HWPXSKILL_SAMPLES=~/rhwp/samples pytest -m samples          # 실제 한글 저장본으로 (선택)
```

개인정보가 든 실제 문서는 저장소에 올리지 않습니다. PyPI 배포는 GitHub 릴리스를 발행하면 `.github/workflows/publish.yml`이 Trusted Publishing으로 올립니다 (PyPI에서 먼저 publisher 등록 필요).

## 라이선스와 출처

MIT. [kordoc](https://github.com/chrisryugj/kordoc)(MIT)의 HWPX 편집 방식·양식 라벨 규칙·공문서 검사 규칙·개인정보 규칙을 옮겼고, [rhwp](https://github.com/edwardkim/rhwp)(MIT)를 PDF 렌더·변환에 씁니다. 자세한 내용은 [NOTICE](NOTICE).
