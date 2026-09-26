---
name: hwpxskill
description: "HWPX 한글 문서 엔진 및 5대 에이전트팀 워크플로 스킬. 템플릿/작성양식을 주면 표, 글씨, 폰트, 양식을 모두 편집하고 적절한 내용까지 자동으로 채워주며, 한컴 OWPML 표준 골든 패키징 및 개인정보(PII)/민감정보 전수 감사를 수행한다. 'hwpx', '한글 양식 채우기', '표 편집', '보고서 생성', 'hwpxskill' 요청 시 사용."
---

# HWPX Skill: Antigravity / Claude Code Swarm Workflow Guide

## 개요 (Overview)
`hwpxskill`은 한컴오피스 한글 HWPX(KS X 6101 OWPML 표준) 문서를 프로그래밍 방식으로 분석, 스타일링(폰트/표/테두리/배경색), 내용 주입, 무결성 패키징 및 개인정보(PII) 감사를 원스톱으로 수행하는 종합 엔진이자 5대 전문 에이전트팀 오케스트레이션 스킬입니다.

---

## 5대 전문 에이전트팀 워크플로 (5-Agent Swarm Team)

```
[Agent 1: Template Analyzer]
   └─ 템플릿의 표, 행/열 크기, cellAddr 좌표, 빈칸(empty_cell), 플레이스홀더(${...}, {{...}}, [항목]) 전수 추출
          ↓
[Agent 2: Content Architect]
   └─ 사용자 지시(instruction)와 주제에 부합하는 전문적이고 논리적인 항목별 내용 및 매핑 설계
          ↓
[Agent 3: Style Formatter]
   └─ 글꼴, 글자 크기, 색상, 볼드(charPr), 문단 정렬(paraPr), 표 열너비 비율, 테두리, 셀 배경음영(borderFill) 정밀 스타일링
          ↓
[Agent 4: Document Assembler]
   └─ DOM 트리에 텍스트 및 멀티라인 주입, linesegarray 캐시 무효화, mimetype STORED 첫 엔트리 골든 패키징
          ↓
[Agent 5: Quality & Privacy Auditor]
   └─ 한컴 뷰어 렌더링 무결성, 잔존 플레이스홀더 점검, 수식/합계 검산, 개인정보(전화번호/주민번호/토큰/실명) 전수 차단 감사
```

---

## Python API 사용법

```python
from hwpxskill import (
    HwpxAnalyzer,
    HwpxStyler,
    HwpxEditor,
    HwpxValidator,
    HwpxTeamWorkflow,
    run_pipeline,
)

# 1. 5대 에이전트팀 원스톱 실행
result = run_pipeline(
    template_hwpx="template.hwpx",
    user_prompt="2026년도 AI 교수학습 운영 계획서 작성",
    output_hwpx="result.hwpx",
    content_data={
        "fills": {
            "s0.t0.r1.c1": "AI 기반 맞춤형 학습",
            "s0.t0.r2.c1": "개념기반 탐구 활동 및 피드백 강화",
        },
        "replacements": {
            "{{기관명}}": "한국교육혁신원",
            "{{작성일}}": "2026. 09. 26.",
        }
    },
    style_config={
        "col_widths": [12000, 36000],
        "total_width": 48000,
    }
)
print("Pipeline Status:", result["status"])
print("Audit Report:", result["audit_report"])
```

---

## CLI 명령행 인터페이스

```bash
# 1. 템플릿 구조 및 빈칸 분석
hwpxskill analyze template.hwpx --json

# 2. 데이터 기반 내용 채우기
hwpxskill fill template.hwpx output.hwpx --data data.json

# 3. 표 너비, 테두리, 배경색, 스타일 서식 조정
hwpxskill format-table input.hwpx output.hwpx --config style.json

# 4. 개인정보(PII) 및 골든 패키징 무결성 감사
hwpxskill audit output.hwpx

# 5. 5대 에이전트팀 풀 파이프라인 구동
hwpxskill team-run template.hwpx output.hwpx --instruction "공식 업무 보고서 작성" --data data.json
```

---

## 핵심 엔지니어링 원칙 (Core Rules)
1. **양식 및 메타데이터 보존**: 기존 템플릿의 `content.hpf` 등 메타데이터를 파괴하지 않고 section XML과 필요한 header XML 항목만 정밀 갱신합니다.
2. **골든 패키징 룰 준수**: `mimetype` 파일이 압축파일(ZIP)의 반드시 첫 번째 엔트리여야 하며 무압축(`ZIP_STORED`)으로 저장되어야 macOS/Windows 한컴오피스 및 뷰어에서 오류 없이 열립니다.
3. **엄격한 개인정보(PII) 스크러빙**: 전화번호, 주민번호, 특정인 실명, API 키 등의 노출을 `HwpxValidator`를 통해 사전 차단합니다.
