"""HWPX Document Analyzer.

Extracts table layouts, cell addresses, placeholder patterns, and style metadata.
"""
from __future__ import annotations

import re
import zipfile
from typing import Any, Dict, List, Optional
import xml.etree.ElementTree as ET

from .core.namespace import NS, HP, HH, HC, HS, register_all_namespaces


class HwpxAnalyzer:
    """Analyzes HWPX document contents, table structures, placeholders, and styles."""

    def __init__(self, hwpx_path: str):
        self.hwpx_path = hwpx_path
        register_all_namespaces()

    def _read_xml(self, zip_ref: zipfile.ZipFile, filename: str) -> Optional[ET.Element]:
        try:
            with zip_ref.open(filename) as f:
                return ET.parse(f).getroot()
        except KeyError:
            return None

    def analyze(self) -> Dict[str, Any]:
        """Performs a comprehensive structural and stylistic analysis of the HWPX file."""
        report: Dict[str, Any] = {
            "tables": [],
            "placeholders": [],
            "styles": {
                "charPr": {},
                "paraPr": {},
                "borderFill": {},
            },
            "summary": {
                "table_count": 0,
                "placeholder_count": 0,
                "section_count": 0,
            },
        }

        with zipfile.ZipFile(self.hwpx_path, "r") as zf:
            header_root = self._read_xml(zf, "Contents/header.xml")
            if header_root is not None:
                self._analyze_header(header_root, report)

            section_idx = 0
            while True:
                filename = f"Contents/section{section_idx}.xml"
                if filename not in zf.namelist():
                    break
                section_root = self._read_xml(zf, filename)
                if section_root is not None:
                    self._analyze_section(section_root, section_idx, report)
                section_idx += 1

            report["summary"]["section_count"] = section_idx
            report["summary"]["table_count"] = len(report["tables"])
            report["summary"]["placeholder_count"] = len(report["placeholders"])

        return report

    def _analyze_header(self, root: ET.Element, report: Dict[str, Any]) -> None:
        for char_pr in root.findall(".//hh:charPr", NS):
            pr_id = char_pr.get("id")
            if pr_id is not None:
                font_ref = char_pr.find("hh:fontRef", NS)
                report["styles"]["charPr"][pr_id] = {
                    "height": char_pr.get("height"),
                    "textColor": char_pr.get("textColor"),
                    "hangul_font": font_ref.get("hangul") if font_ref is not None else None,
                    "latin_font": font_ref.get("latin") if font_ref is not None else None,
                    "bold": char_pr.find("hh:bold", NS) is not None,
                    "italic": char_pr.find("hh:italic", NS) is not None,
                }

        for para_pr in root.findall(".//hh:paraPr", NS):
            pr_id = para_pr.get("id")
            if pr_id is not None:
                align = para_pr.find("hh:align", NS)
                report["styles"]["paraPr"][pr_id] = {
                    "horizontal": align.get("horizontal") if align is not None else None,
                    "lineSpacing": para_pr.get("lineSpacing"),
                }

        for border_fill in root.findall(".//hh:borderFill", NS):
            pr_id = border_fill.get("id")
            if pr_id is not None:
                fill_brush = border_fill.find(".//hc:fillBrush/hc:winBrush", NS)
                report["styles"]["borderFill"][pr_id] = {
                    "faceColor": fill_brush.get("faceColor") if fill_brush is not None else None,
                }

    def _analyze_section(self, root: ET.Element, section_idx: int, report: Dict[str, Any]) -> None:
        placeholder_regex = re.compile(r"(\$\{[^}]+\}|\{\{.*?\}\}|\[[^\]]+\]|_{3,})")

        tables = root.findall(".//hp:tbl", NS)

        for tbl_idx, tbl in enumerate(tables):
            tbl_info: Dict[str, Any] = {
                "section": section_idx,
                "table_index": tbl_idx,
                "rows": 0,
                "cols": 0,
                "cells": [],
            }

            rows = tbl.findall(".//hp:tr", NS)
            tbl_info["rows"] = len(rows)

            max_cols = 0
            for r_idx, row in enumerate(rows):
                cells = row.findall("hp:tc", NS)
                if len(cells) > max_cols:
                    max_cols = len(cells)

                for c_idx, cell in enumerate(cells):
                    cell_addr = cell.find("hp:cellAddr", NS)
                    row_addr = int(cell_addr.get("rowAddr")) if cell_addr is not None and cell_addr.get("rowAddr") else r_idx
                    col_addr = int(cell_addr.get("colAddr")) if cell_addr is not None and cell_addr.get("colAddr") else c_idx

                    cell_sz = cell.find("hp:cellSz", NS)
                    width = int(cell_sz.get("width")) if cell_sz is not None and cell_sz.get("width") else None
                    height = int(cell_sz.get("height")) if cell_sz is not None and cell_sz.get("height") else None

                    texts = [t.text for t in cell.findall(".//hp:t", NS) if t.text]
                    full_text = "".join(texts).strip()

                    cell_info = {
                        "row": row_addr,
                        "col": col_addr,
                        "width": width,
                        "height": height,
                        "borderFillIDRef": cell.get("borderFillIDRef"),
                        "text": full_text,
                        "is_empty": len(full_text) == 0,
                    }
                    tbl_info["cells"].append(cell_info)

                    # Identify empty cell as a blank
                    if not full_text:
                        report["placeholders"].append({
                            "kind": "empty_cell",
                            "location": f"s{section_idx}.t{tbl_idx}.r{row_addr}.c{col_addr}",
                            "section": section_idx,
                            "table": tbl_idx,
                            "row": row_addr,
                            "col": col_addr,
                        })
                    else:
                        matches = placeholder_regex.findall(full_text)
                        for match in matches:
                            report["placeholders"].append({
                                "kind": "pattern",
                                "token": match,
                                "location": f"s{section_idx}.t{tbl_idx}.r{row_addr}.c{col_addr}",
                                "section": section_idx,
                                "table": tbl_idx,
                                "row": row_addr,
                                "col": col_addr,
                                "text": full_text,
                            })

            tbl_info["cols"] = max_cols
            report["tables"].append(tbl_info)

        # Standalone paragraph placeholder search (outside tables)
        for p_idx, p in enumerate(root.findall(".//hp:p", NS)):
            texts = [t.text for t in p.findall(".//hp:t", NS) if t.text]
            p_text = "".join(texts).strip()
            matches = placeholder_regex.findall(p_text)
            for match in matches:
                report["placeholders"].append({
                    "kind": "paragraph_pattern",
                    "token": match,
                    "location": f"s{section_idx}.p{p_idx}",
                    "section": section_idx,
                    "text": p_text,
                })
