"""Quickstart example demonstrating hwpxskill 5-agent team workflow.

This example creates a compliant sample template, runs the full 5-agent pipeline,
and audits the final document for PII and packaging integrity.
"""
import sys
from pathlib import Path

# Add project root and src to sys.path
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "src"))
sys.path.insert(0, str(_ROOT))

from hwpxskill import run_pipeline, HwpxValidator
from tests.conftest import build_sample_hwpx



def main():
    base_dir = Path(__file__).resolve().parent
    template_path = base_dir / "sample_report_template.hwpx"
    output_path = base_dir / "generated_official_report.hwpx"

    print("1. Creating baseline sample HWPX template...")
    build_sample_hwpx(template_path)

    print("\n2. Executing 5-Agent Swarm Workflow...")
    content_data = {
        "fills": {
            "s0.t0.r2.c1": "1. 핵심 개념 구조화 및 탐구 질문 개발\n2. 학생 주도 맞춤형 피드백 루프 구축",
        },
        "replacements": {
            "{{REPORT_TITLE}}": "2026학년도 미래역량 중심 교수학습 운영 계획서",
            "{{DATE}}": "2026. 09. 26.",
            "${GOAL_DESC}": "학생 맞춤형 개념기반 탐구 수업 및 역량 중심 과정평가 내실화",
        }
    }

    style_config = {
        "col_widths": [14000, 34000],
        "total_width": 48000,
    }

    result = run_pipeline(
        template_hwpx=str(template_path),
        user_prompt="2026 미래역량 중심 교수학습 운영 계획서 공식 문서 생성",
        output_hwpx=str(output_path),
        style_config=style_config,
        content_data=content_data,
    )

    print("\n3. Execution Summary:")
    print(f" - Output File: {result['output_file']}")
    print(f" - Applied Actions: {result['applied_actions']}")
    print(f" - Packaging Status: {result['audit_report']['packaging']['message']}")
    print(f" - Privacy Scan Issues: {result['audit_report']['privacy_audit']['issues_count']}")


if __name__ == "__main__":
    main()
