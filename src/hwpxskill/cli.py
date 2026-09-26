"""HWPX Document Engine Command Line Interface.

Provides CLI commands for analysis, styling, editing, privacy auditing, and agent-team runs.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .analyzer import HwpxAnalyzer
from .styler import HwpxStyler
from .editor import HwpxEditor
from .validator import HwpxValidator
from .workflows.orchestrator import run_pipeline


def parse_args():
    parser = argparse.ArgumentParser(
        prog="hwpxskill",
        description="HWPX Document Engine & Multi-Agent Swarm Workflows",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # 1. analyze
    analyze_parser = subparsers.add_parser("analyze", help="Analyze HWPX template structure and styles")
    analyze_parser.add_argument("template_hwpx", help="Path to input HWPX template")
    analyze_parser.add_argument("--json", action="store_true", help="Print structured report in JSON")

    # 2. fill
    fill_parser = subparsers.add_parser("fill", help="Fill HWPX template with JSON data")
    fill_parser.add_argument("template_hwpx", help="Path to input HWPX template")
    fill_parser.add_argument("output_hwpx", help="Path to destination HWPX file")
    fill_parser.add_argument("--data", required=True, help="Path to content data JSON file")

    # 3. format-table
    format_parser = subparsers.add_parser("format-table", help="Format table width, borders and styles")
    format_parser.add_argument("input_hwpx", help="Path to input HWPX file")
    format_parser.add_argument("output_hwpx", help="Path to output HWPX file")
    format_parser.add_argument("--config", required=True, help="Path to table format config JSON")

    # 4. audit
    audit_parser = subparsers.add_parser("audit", help="Audit HWPX for packaging standards and PII leaks")
    audit_parser.add_argument("hwpx_file", help="Path to HWPX file to audit")
    audit_parser.add_argument("--json", action="store_true", help="Print audit report in JSON")

    # 5. team-run
    team_parser = subparsers.add_parser("team-run", help="Execute complete 5-agent team workflow")
    team_parser.add_argument("template_hwpx", help="Path to input HWPX template")
    team_parser.add_argument("output_hwpx", help="Path to destination HWPX file")
    team_parser.add_argument("--instruction", required=True, help="User instruction or prompt")
    team_parser.add_argument("--data", required=True, help="Path to content mapping JSON")
    team_parser.add_argument("--style", help="Optional path to styling configuration JSON")

    return parser.parse_args()


def main():
    args = parse_args()

    if args.command == "analyze":
        analyzer = HwpxAnalyzer(args.template_hwpx)
        report = analyzer.analyze()
        if args.json:
            print(json.dumps(report, indent=2, ensure_ascii=False))
        else:
            print(f"HWPX Analysis Report: {args.template_hwpx}")
            print(f" - Tables: {report['summary']['table_count']}")
            print(f" - Placeholders: {report['summary']['placeholder_count']}")
            print(f" - Character Styles: {len(report['styles']['charPr'])}")
            print(f" - Border/Fill Styles: {len(report['styles']['borderFill'])}")

    elif args.command == "fill":
        with open(args.data, "r", encoding="utf-8") as f:
            data = json.load(f)
        editor = HwpxEditor()
        fills = data.get("fills", {})
        replacements = data.get("replacements", {})
        if not fills and not replacements:
            for k, v in data.items():
                if any(k.startswith(p) for p in ["s", "t", "r"]):
                    fills[k] = v
                else:
                    replacements[k] = v

        count = editor.fill_document(
            src_hwpx=args.template_hwpx,
            dst_hwpx=args.output_hwpx,
            fills=fills,
            replacements=replacements,
        )
        print(f"Document populated with {count} modifications -> {args.output_hwpx}")

    elif args.command == "format-table":
        with open(args.config, "r", encoding="utf-8") as f:
            config = json.load(f)
        styler = HwpxStyler()
        changed = styler.apply_table_format_file(
            src_hwpx=args.input_hwpx,
            dst_hwpx=args.output_hwpx,
            table_config=config,
        )
        print(f"Table formatted ({changed} cells modified) -> {args.output_hwpx}")

    elif args.command == "audit":
        validator = HwpxValidator(args.hwpx_file)
        report = validator.audit_document()
        if args.json:
            print(json.dumps(report, indent=2, ensure_ascii=False))
        else:
            print(f"HWPX Security & Quality Audit: {args.hwpx_file}")
            print(f" - Overall Status: {report['status']}")
            print(f" - Packaging: {'VALID' if report['packaging']['valid'] else 'INVALID'} ({report['packaging']['message']})")
            print(f" - PII / Secret Leaks: {report['privacy_audit']['issues_count']} detected")
            if report['privacy_audit']['findings']:
                for item in report['privacy_audit']['findings']:
                    print(f"   [!] {item['type']} in {item['file']}: {item['match']}")
            print(f" - Residual Placeholders: {report['residual_placeholders']['count']} unfilled")

    elif args.command == "team-run":
        with open(args.data, "r", encoding="utf-8") as f:
            data = json.load(f)
        style_cfg = None
        if args.style:
            with open(args.style, "r", encoding="utf-8") as f:
                style_cfg = json.load(f)

        result = run_pipeline(
            template_hwpx=args.template_hwpx,
            user_prompt=args.instruction,
            output_hwpx=args.output_hwpx,
            style_config=style_cfg,
            content_data=data,
        )
        print(f"\nSwarm Execution Finished: {result['status'].upper()}")
        print(f"Output File: {result['output_file']}")


if __name__ == "__main__":
    main()
