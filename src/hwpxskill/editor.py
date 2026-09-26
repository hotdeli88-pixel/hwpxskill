"""HWPX Content Editor & Form Filling Engine.

Injects text into cells by coordinates (<hp:cellAddr>), replaces placeholders,
and manages bullet lists while strictly preserving surrounding font and layout properties.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple, Union
import xml.etree.ElementTree as ET

from .core.namespace import NS, HP, register_all_namespaces
from .core.package import unpack_hwpx, repack_hwpx, write_with_lock_fallback


class HwpxEditor:
    """Edits and populates HWPX document contents, preserving table layouts and cell properties."""

    def __init__(self):
        register_all_namespaces()

    def find_cell(self, tbl: ET.Element, row: int, col: int) -> Optional[ET.Element]:
        """Finds cell by <hp:cellAddr rowAddr, colAddr> or falls back to grid index."""
        # 1. Coordinate check
        for cell in tbl.findall(".//hp:tc", NS):
            addr = cell.find("hp:cellAddr", NS)
            if addr is not None:
                if addr.get("rowAddr") == str(row) and addr.get("colAddr") == str(col):
                    return cell

        # 2. Grid fallback
        rows = tbl.findall(".//hp:tr", NS)
        if 0 <= row < len(rows):
            cells = rows[row].findall("hp:tc", NS)
            if 0 <= col < len(cells):
                return cells[col]

        return None

    def _borrow_charpr_id(self, tbl: ET.Element) -> str:
        """Borrows any existing charPrIDRef from the table to maintain typography."""
        for run in tbl.iter(f"{HP}run"):
            ref = run.get("charPrIDRef")
            if ref is not None:
                return ref
        return "0"

    def fill_cell_by_addr(
        self,
        tbl: ET.Element,
        row: int,
        col: int,
        text: str,
        charpr_id: Optional[str] = None,
        parapr_id: Optional[str] = None,
    ) -> bool:
        """Injects text into the cell at (row, col), splitting multiple lines into paragraphs."""
        cell = self.find_cell(tbl, row, col)
        if cell is None:
            return False

        # Find target container (subList or cell itself)
        container = cell.find("hp:subList", NS)
        if container is None:
            container = cell

        # Borrow style if not specified
        existing_run = cell.find(".//hp:run", NS)
        if charpr_id is None:
            charpr_id = existing_run.get("charPrIDRef") if existing_run is not None else self._borrow_charpr_id(tbl)

        existing_p = cell.find(".//hp:p", NS)
        if parapr_id is None:
            parapr_id = existing_p.get("paraPrIDRef") if existing_p is not None else "0"

        # Remove existing paragraphs
        for p in list(container):
            if p.tag.endswith("}p"):
                container.remove(p)

        # Create new paragraphs for each line
        lines = str(text).split("\n")
        for line in lines:
            p_elem = ET.SubElement(container, f"{HP}p", {
                "id": "4294967295",
                "paraPrIDRef": str(parapr_id),
                "styleIDRef": "0",
                "pageBreak": "0",
                "columnBreak": "0",
                "merged": "0",
            })
            run_elem = ET.SubElement(p_elem, f"{HP}run", {
                "charPrIDRef": str(charpr_id)
            })
            t_elem = ET.SubElement(run_elem, f"{HP}t")
            t_elem.text = line

        return True

    def replace_text(self, element: ET.Element, mapping: Dict[str, str]) -> int:
        """Replaces placeholder occurrences inside all <hp:t> tags of the element."""
        count = 0
        for t_elem in element.findall(".//hp:t", NS):
            if t_elem.text:
                orig_text = t_elem.text
                new_text = orig_text
                for k, v in mapping.items():
                    if k in new_text:
                        new_text = new_text.replace(k, str(v))
                if new_text != orig_text:
                    t_elem.text = new_text
                    count += 1
        return count

    def replace_cell_text(self, tbl: ET.Element, row: int, col: int, mapping: Dict[str, str]) -> int:
        """Applies string replacements exclusively within the cell at (row, col)."""
        cell = self.find_cell(tbl, row, col)
        if cell is None:
            return 0
        return self.replace_text(cell, mapping)

    def fill_bullets(
        self,
        tbl: ET.Element,
        row: int,
        col: int,
        items: List[str],
        marker: str = "-",
    ) -> bool:
        """Fills a list of items as bullet lines in the specified cell."""
        text = "\n".join([f"{marker} {item.strip()}" for item in items if item.strip()])
        return self.fill_cell_by_addr(tbl, row, col, text)

    def fill_document(
        self,
        src_hwpx: str,
        dst_hwpx: str,
        fills: Optional[Dict[str, Any]] = None,
        replacements: Optional[Dict[str, str]] = None,
    ) -> int:
        """High-level document filler supporting cell coordinates, IDs, and string replacements."""
        entries = unpack_hwpx(src_hwpx)
        fills = fills or {}
        replacements = replacements or {}
        total_actions = 0

        for name, data in list(entries.items()):
            if not (name.startswith("Contents/section") and name.endswith(".xml")):
                continue

            root = ET.fromstring(data)
            tables = root.findall(".//hp:tbl", NS)

            # 1. Apply global replacements in this section
            if replacements:
                total_actions += self.replace_text(root, replacements)

            # 2. Apply structured fills
            # Format: "s{sec}.t{tbl}.r{row}.c{col}": "value" or "t{tbl}.r{row}.c{col}"
            for key, val in fills.items():
                parts = key.split(".")
                tbl_idx = 0
                r_idx = -1
                c_idx = -1

                for part in parts:
                    if part.startswith("t") and part[1:].isdigit():
                        tbl_idx = int(part[1:])
                    elif part.startswith("r") and part[1:].isdigit():
                        r_idx = int(part[1:])
                    elif part.startswith("c") and part[1:].isdigit():
                        c_idx = int(part[1:])

                if r_idx >= 0 and c_idx >= 0 and tbl_idx < len(tables):
                    if self.fill_cell_by_addr(tables[tbl_idx], r_idx, c_idx, str(val)):
                        total_actions += 1

            entries[name] = ET.tostring(root, encoding="utf-8", xml_declaration=True)

        repack_hwpx(entries, dst_hwpx)
        return total_actions
