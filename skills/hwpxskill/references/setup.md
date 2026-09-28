# 설치와 실행 환경

엔진은 **Python 3.9 이상, 표준 라이브러리만** 쓴다. 양식 분석·채우기·표 스타일·수식·시험지·검사는 어디서나 된다.
PDF 렌더(검수)와 HWP 변환만 외부 프로그램이 필요하다.

| 환경 | PDF 렌더·HWP 변환 | 준비 |
|---|---|---|
| Windows + 한글 2022 이상 | 한글 자동화(COM) | pywin32, (권장) 보안 모듈 등록 |
| Mac + 한글 for Mac | rhwp | rhwp 설치 (한글 for Mac은 자동화를 지원하지 않음) |
| Linux | rhwp | rhwp 설치 |

설치 뒤 확인: `python3 <스킬 폴더>/scripts/hwpx.py doctor`

## 스킬 설치

### Claude Code 플러그인
```
/plugin marketplace add hotdeli88-pixel/hwpxskill
/plugin install hwpxskill@hwpxskill
```

### 폴더 복사 (Claude Code 개인·프로젝트 스킬, Antigravity 등 다른 도구)
`skills/hwpxskill` 폴더(SKILL.md, scripts, references, hwpxskill)를 통째로 복사한다.
- Claude Code: `~/.claude/skills/hwpxskill/` (모든 프로젝트) 또는 `<프로젝트>/.claude/skills/hwpxskill/`
- Antigravity 등: 그 도구의 스킬·규칙 폴더에 두거나, 작업 폴더에 두고 에이전트 지침(AGENTS.md 등)에 "한글 문서 작업은 `hwpxskill/SKILL.md`를 읽고 따른다"를 적는다. 명령은 `python3 hwpxskill/scripts/hwpx.py …`로 같다.

### pip (명령줄 도구·파이썬 라이브러리)
```bash
pip install hwpxskill                                            # PyPI 배포 후
pip install "git+https://github.com/hotdeli88-pixel/hwpxskill"    # 저장소에서 바로
hwpxskill doctor
```
Windows 한글 자동화까지: `pip install "hwpxskill[windows]"` (pywin32 포함).

## Windows — 한글 자동화

1. 한글 2022 이상 설치 (정품 인증된 상태).
2. `scripts/setup_windows.ps1` 실행:
   ```powershell
   powershell -ExecutionPolicy Bypass -File <스킬 폴더>\scripts\setup_windows.ps1
   ```
   pywin32를 설치하고 `doctor`로 점검한다.
3. (권장) **보안 모듈 등록** — 등록하지 않으면 파일을 열고 저장할 때마다 "접근 허용" 창이 떠서 자동 작업이 멈춘다.
   - 한컴 개발자 사이트(developer.hancom.com)의 '한글 자동화' 자료에서 보안 모듈(`FilePathCheckerModuleExample.dll`)을 받아 고정된 폴더에 둔다.
   - `setup_windows.ps1 -DllPath "C:\HwpAutomation\FilePathCheckerModuleExample.dll"` — 현재 사용자 레지스트리 `HKCU\Software\HNC\HwpAutomation\Modules`에 `FilePathCheckerModule` 값으로 등록한다.
4. 한글이 열어 둔 파일에는 저장할 수 없으니, 결과 파일은 한글에서 닫은 상태로 둔다 (잠겨 있으면 `_v1` 이름으로 저장됨).

한글 자동화가 안 되면 rhwp를 대신 쓴다: [릴리스 페이지](https://github.com/edwardkim/rhwp/releases)에서 `rhwp-*-windows-x86_64.zip`을 받아 풀고 `HWPXSKILL_RHWP` 환경 변수에 `rhwp.exe` 경로를 넣는다.

## Mac·Linux — rhwp

[rhwp](https://github.com/edwardkim/rhwp)(MIT)는 HWP/HWPX를 읽고 PDF로 그리며 HWP↔HWPX를 변환한다.

```bash
bash <스킬 폴더>/scripts/install_rhwp.sh          # 최신 릴리스 → ~/.local/bin/rhwp (체크섬 확인)
```
- 릴리스를 못 받으면 러스트(`cargo`)가 있을 때 소스에서 빌드한다: `cargo install --git https://github.com/edwardkim/rhwp --bin rhwp rhwp`
- PATH에 없으면 `export HWPXSKILL_RHWP=~/.local/bin/rhwp`
- Mac에서 "확인되지 않은 개발자" 경고가 나면: `xattr -d com.apple.quarantine ~/.local/bin/rhwp`

### 글꼴
rhwp PDF는 설치된 글꼴로 그린다. 한글 글꼴(함초롬바탕·돋움 등)이 없으면 비슷한 글꼴로 대신 그려 줄바꿈이 한글과 조금 다를 수 있다.
- 한글 for Mac이 있으면 그 글꼴 폴더를 알려 준다: `export HWPXSKILL_FONT_PATH="/폴더1:/폴더2"`
- 수식 글꼴(HYhwpEQ)이 없으면 엔진이 대체 수식 글꼴을 자동으로 지정한다 (`doctor`에 표시). 직접 정하려면 `export HWPXSKILL_EQ_FONT="Times New Roman"`.

## 환경 변수

| 변수 | 뜻 |
|---|---|
| `HWPXSKILL_RHWP` | rhwp 실행 파일 경로 |
| `HWPXSKILL_FONT_PATH` | rhwp PDF 글꼴 폴더 (`:` 구분, Windows는 `;`) |
| `HWPXSKILL_EQ_FONT` | rhwp PDF 수식 글꼴 |

## 문제 해결

| 증상 | 확인 |
|---|---|
| `doctor`에 PDF 렌더 "아니요" | Windows: pywin32·한글 설치, Mac·Linux: rhwp 설치·`HWPXSKILL_RHWP` |
| Windows에서 창이 떠서 멈춤 | 보안 모듈 등록 (위 3번) |
| PDF에서 수식이 빈 네모 | `doctor`의 수식 글꼴 확인, `HWPXSKILL_EQ_FONT` 지정 |
| `python3`이 없음 (Windows) | `py -3` 또는 `python`으로 실행 |
| 한글 깨짐(Windows 콘솔) | 엔진이 UTF-8로 출력함 — 터미널을 UTF-8로(`chcp 65001`) |
