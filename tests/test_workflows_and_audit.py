"""Workflow orchestration and security audit tests for hwpxskill."""
from pathlib import Path
import json
import zipfile

import pytest
from hwpxskill import HwpxTeamWorkflow, HwpxValidator, run_pipeline
from hwpxskill.core.package import unpack_hwpx, repack_hwpx


def test_team_workflow_pipeline(sample_hwpx: Path, tmp_path: Path):
    """Test full 5-agent team workflow execution from template to audited output."""
    out_file = tmp_path / "team_output.hwpx"

    content_data = {
        "fills": {
            "s0.t0.r2.c1": "프로젝트 중심 수업 구현\n협력적 문제 해결",
        },
        "replacements": {
            "{{REPORT_TITLE}}": "2026 미래교육 혁신 실행계획",
            "{{DATE}}": "2026. 09. 26.",
            "${GOAL_DESC}": "디지털 전환 및 창의적 탐구 역량 강화",
        }
    }

    result = run_pipeline(
        template_hwpx=str(sample_hwpx),
        user_prompt="2026 미래교육 혁신 실행계획 문서 생성",
        output_hwpx=str(out_file),
        content_data=content_data,
    )

    assert result["status"] == "success"
    assert out_file.exists()
    assert result["audit_report"]["packaging"]["valid"] is True
    assert result["audit_report"]["privacy_audit"]["issues_count"] == 0


def test_privacy_auditor_pii_detection(sample_hwpx: Path, tmp_path: Path):
    """Verify that HwpxValidator catches phone numbers, SSNs, and API keys."""
    # 1. Clean file audit
    clean_validator = HwpxValidator(str(sample_hwpx))
    clean_report = clean_validator.audit_document()
    assert clean_report["privacy_audit"]["issues_count"] == 0

    # 2. Inject PII into temporary HWPX
    pii_file = tmp_path / "leaky_document.hwpx"
    entries = unpack_hwpx(sample_hwpx)
    sec0_str = entries["Contents/section0.xml"].decode("utf-8")
    sec0_str = sec0_str.replace("추진 목표", "담당교사: 홍길동 (010-1234-5678, 850101-1234567)")
    sec0_str = sec0_str.replace("실행 계획", "인증키: Bearer 1234567890abcdefghijklmnopqrstuvwxyz")
    entries["Contents/section0.xml"] = sec0_str.encode("utf-8")
    repack_hwpx(entries, pii_file)

    # 3. Audit leaky file
    leaky_validator = HwpxValidator(str(pii_file))
    leaky_report = leaky_validator.audit_document()
    issues = leaky_report["privacy_audit"]["findings"]

    issue_types = [item["type"] for item in issues]
    assert "phone_mobile" in issue_types
    assert "resident_id" in issue_types
    assert "bearer_token" in issue_types
    assert leaky_report["status"] == "WARN"



def test_cli_execution(sample_hwpx: Path, tmp_path: Path):
    """Test CLI commands execution."""
    import subprocess
    import sys

    # hwpxskill analyze --json
    res_analyze = subprocess.run(
        [sys.executable, "-m", "hwpxskill.cli", "analyze", str(sample_hwpx), "--json"],
        capture_output=True,
        text=True,
        check=True,
    )
    report = json.loads(res_analyze.stdout)
    assert report["summary"]["table_count"] == 1

    # hwpxskill audit
    res_audit = subprocess.run(
        [sys.executable, "-m", "hwpxskill.cli", "audit", str(sample_hwpx), "--json"],
        capture_output=True,
        text=True,
        check=True,
    )
    audit_data = json.loads(res_audit.stdout)
    assert audit_data["packaging"]["valid"] is True
