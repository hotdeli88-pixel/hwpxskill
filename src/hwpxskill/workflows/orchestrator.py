"""HWPX Multi-Agent Swarm Orchestration Engine.

Coordinates 5 specialized agents to analyze templates, architect content, apply styles,
assemble valid HWPX documents, and audit privacy and packaging integrity.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from ..analyzer import HwpxAnalyzer
from ..styler import HwpxStyler
from ..editor import HwpxEditor
from ..validator import HwpxValidator
from ..core.package import unpack_hwpx, repack_hwpx, write_with_lock_fallback


class HwpxTeamWorkflow:
    """Orchestrates the 5-agent team workflow for end-to-end HWPX generation."""

    def __init__(self):
        self.styler = HwpxStyler()
        self.editor = HwpxEditor()

    def run_pipeline(
        self,
        template_hwpx: str,
        user_prompt: str,
        output_hwpx: str,
        style_config: Optional[Dict[str, Any]] = None,
        content_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Executes the full 5-agent pipeline."""
        print(f"[Workflow] Initializing Swarm Pipeline: {template_hwpx} -> {output_hwpx}")

        # ---------------------------------------------------------------------
        # Agent 1: Template Analyzer
        # ---------------------------------------------------------------------
        print("[Agent 1 · Template Analyzer] Scanning document structure, tables, and blank placeholders...")
        analyzer = HwpxAnalyzer(template_hwpx)
        analysis_report = analyzer.analyze()
        print(f"  -> Found {analysis_report['summary']['table_count']} tables, "
              f"{analysis_report['summary']['placeholder_count']} placeholders.")

        # ---------------------------------------------------------------------
        # Agent 2: Content Architect
        # ---------------------------------------------------------------------
        print("[Agent 2 · Content Architect] Designing document structure and content mapping...")
        content_data = content_data or {}
        fills = content_data.get("fills", {})
        replacements = content_data.get("replacements", {})

        # If simple dict passed without 'fills'/'replacements' keys, categorize them
        if not fills and not replacements and content_data:
            for k, v in content_data.items():
                if any(k.startswith(prefix) for prefix in ["s", "t", "r"]):
                    fills[k] = v
                else:
                    replacements[k] = v

        print(f"  -> Prepared {len(fills)} cell-level fills, {len(replacements)} text replacements.")

        # ---------------------------------------------------------------------
        # Agent 3: Style Formatter
        # ---------------------------------------------------------------------
        temp_styled = output_hwpx + ".styled.tmp"
        if style_config:
            print("[Agent 3 · Style Formatter] Applying custom typography, table geometry, and border fills...")
            self.styler.apply_table_format_file(
                src_hwpx=template_hwpx,
                dst_hwpx=temp_styled,
                table_config=style_config,
            )
            working_template = temp_styled
        else:
            print("[Agent 3 · Style Formatter] Keeping template's native typography and table styles.")
            working_template = template_hwpx

        # ---------------------------------------------------------------------
        # Agent 4: Document Assembler
        # ---------------------------------------------------------------------
        print("[Agent 4 · Document Assembler] Injecting content and repacking with golden packaging rule...")
        actions = self.editor.fill_document(
            src_hwpx=working_template,
            dst_hwpx=output_hwpx,
            fills=fills,
            replacements=replacements,
        )
        print(f"  -> Successfully applied {actions} content modifications into HWPX DOM.")

        if Path(temp_styled).exists():
            try:
                Path(temp_styled).unlink()
            except OSError:
                pass

        # ---------------------------------------------------------------------
        # Agent 5: Quality & Privacy Auditor
        # ---------------------------------------------------------------------
        print("[Agent 5 · Privacy & Quality Auditor] Running package integrity and PII vulnerability scan...")
        validator = HwpxValidator(output_hwpx)
        audit_report = validator.audit_document()

        pii_issues = audit_report["privacy_audit"]["issues_count"]
        pkg_valid = audit_report["packaging"]["valid"]

        if pii_issues > 0:
            print(f"  [CRITICAL WARNING] Privacy auditor detected {pii_issues} potential PII issue(s)!")
        else:
            print("  [AUDIT PASS] Zero PII or private credentials detected.")

        if not pkg_valid:
            print(f"  [ERROR] Golden packaging rule violation: {audit_report['packaging']['message']}")
        else:
            print("  [AUDIT PASS] HWPX packaging strictly complies with Hancom OWPML standards.")

        return {
            "status": "success" if (pkg_valid and pii_issues == 0) else "warning",
            "output_file": str(Path(output_hwpx).resolve()),
            "analysis_summary": analysis_report["summary"],
            "applied_actions": actions,
            "audit_report": audit_report,
        }


def run_pipeline(
    template_hwpx: str,
    user_prompt: str,
    output_hwpx: str,
    style_config: Optional[Dict[str, Any]] = None,
    content_data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Convenience helper to run the 5-agent team pipeline."""
    workflow = HwpxTeamWorkflow()
    return workflow.run_pipeline(
        template_hwpx=template_hwpx,
        user_prompt=user_prompt,
        output_hwpx=output_hwpx,
        style_config=style_config,
        content_data=content_data,
    )
