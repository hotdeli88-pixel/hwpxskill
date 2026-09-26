"""HWPX Typography and Table Styling Engine.

Handles character styles (fonts, sizes, colors), paragraph alignments, border fills,
and table geometry (widths, column ratios, cell shading).
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple, Union
import xml.etree.ElementTree as ET

from .core.namespace import NS, HP, HH, HC, register_all_namespaces
from .core.package import unpack_hwpx, repack_hwpx, write_with_lock_fallback


class HwpxStyler:
    """Controls styling, fonts, borders, fills, and table dimensions in HWPX documents."""

    def __init__(self):
        register_all_namespaces()

    def add_or_update_charpr(
        self,
        header_bytes: bytes,
        font_name: str = "한컴바탕",
        height_pt: float = 10.0,
        text_color: str = "#000000",
        bold: bool = False,
        italic: bool = False,
        base_id: Optional[str] = None,
    ) -> Tuple[bytes, str]:
        """Registers a character property (font, size, color, bold) in header.xml.

        Returns (updated_header_bytes, charPr_id).
        """
        root = ET.fromstring(header_bytes)
        char_properties = root.find(".//hh:charProperties", NS)
        if char_properties is None:
            char_properties = ET.SubElement(root.find(".//hh:head", NS) or root, f"{HH}charProperties")

        existing = char_properties.findall("hh:charPr", NS)
        new_id = str(max([int(cp.get("id", "0")) for cp in existing], default=-1) + 1)
        height_hwpx = int(height_pt * 100)

        char_pr = ET.SubElement(char_properties, f"{HH}charPr", {
            "id": new_id,
            "height": str(height_hwpx),
            "textColor": text_color,
            "shadeColor": "none",
            "useFontSpace": "0",
            "useKerning": "0",
            "symMark": "0",
            "borderFillIDRef": "0",
        })

        font_ref = ET.SubElement(char_pr, f"{HH}fontRef", {
            "hangul": font_name,
            "latin": font_name,
            "hanja": font_name,
            "japanese": font_name,
            "other": font_name,
            "symbol": font_name,
            "user": font_name,
        })
        ratio = ET.SubElement(char_pr, f"{HH}ratio", {k: "100" for k in ["hangul", "latin", "hanja", "japanese", "other", "symbol", "user"]})
        spacing = ET.SubElement(char_pr, f"{HH}spacing", {k: "0" for k in ["hangul", "latin", "hanja", "japanese", "other", "symbol", "user"]})
        rel_sz = ET.SubElement(char_pr, f"{HH}relSz", {k: "100" for k in ["hangul", "latin", "hanja", "japanese", "other", "symbol", "user"]})
        offset = ET.SubElement(char_pr, f"{HH}offset", {k: "0" for k in ["hangul", "latin", "hanja", "japanese", "other", "symbol", "user"]})

        if bold:
            ET.SubElement(char_pr, f"{HH}bold")
        if italic:
            ET.SubElement(char_pr, f"{HH}italic")

        char_properties.set("itemCnt", str(len(char_properties.findall("hh:charPr", NS))))
        return ET.tostring(root, encoding="utf-8", xml_declaration=True), new_id

    def add_or_update_borderfill(
        self,
        header_bytes: bytes,
        fill_color: Optional[str] = None,
        border_type: str = "SOLID",
        border_width: str = "0.12 mm",
        border_color: str = "#000000",
    ) -> Tuple[bytes, str]:
        """Registers a border and cell background color in header.xml.

        Returns (updated_header_bytes, borderFill_id).
        """
        root = ET.fromstring(header_bytes)
        border_fills = root.find(".//hh:borderFills", NS)
        if border_fills is None:
            border_fills = ET.SubElement(root.find(".//hh:head", NS) or root, f"{HH}borderFills")

        existing = border_fills.findall("hh:borderFill", NS)
        new_id = str(max([int(bf.get("id", "0")) for bf in existing], default=-1) + 1)

        bf_elem = ET.SubElement(border_fills, f"{HH}borderFill", {
            "id": new_id,
            "threeD": "0",
            "shadow": "0",
            "centerLine": "NONE",
            "breakCellSeparateLine": "0",
        })

        ET.SubElement(bf_elem, f"{HH}slash", {"type": "NONE", "Crooked": "0", "isCounter": "0"})
        ET.SubElement(bf_elem, f"{HH}backSlash", {"type": "NONE", "Crooked": "0", "isCounter": "0"})

        for side in ["leftBorder", "rightBorder", "topBorder", "bottomBorder"]:
            t_type = border_type if border_width != "0 mm" else "NONE"
            ET.SubElement(bf_elem, f"{HH}{side}", {
                "type": t_type,
                "width": border_width,
                "color": border_color,
            })

        if fill_color:
            fill_brush = ET.SubElement(bf_elem, f"{HC}fillBrush")
            ET.SubElement(fill_brush, f"{HC}winBrush", {
                "faceColor": fill_color,
                "hatchColor": "#FF000000",
                "alpha": "0",
            })

        border_fills.set("itemCnt", str(len(border_fills.findall("hh:borderFill", NS))))
        return ET.tostring(root, encoding="utf-8", xml_declaration=True), new_id

    def format_table(
        self,
        tbl: ET.Element,
        col_widths: Optional[List[int]] = None,
        total_width: Optional[int] = None,
        header_charpr: Optional[str] = None,
        data_charpr: Optional[str] = None,
        header_borderfill: Optional[str] = None,
        data_borderfill: Optional[str] = None,
        header_parapr: Optional[str] = None,
        data_parapr: Optional[str] = None,
    ) -> int:
        """Applies width normalization, styles, and borders to a table element."""
        if total_width is not None:
            sz = tbl.find("hp:sz", NS)
            if sz is not None:
                sz.set("width", str(total_width))
            tbl.set("noAdjust", "1")

        rows = tbl.findall(".//hp:tr", NS)
        nrows = len(rows)
        changes = 0

        for r_idx, row in enumerate(rows):
            is_header = (r_idx == 0)
            cells = row.findall("hp:tc", NS)

            for c_idx, cell in enumerate(cells):
                # Set cell width
                if col_widths and c_idx < len(col_widths):
                    cell_sz = cell.find("hp:cellSz", NS)
                    if cell_sz is not None:
                        cell_sz.set("width", str(col_widths[c_idx]))

                # Set header attribute
                cell.set("header", "1" if is_header else "0")

                # Set borderFill
                bf_to_use = header_borderfill if is_header else data_borderfill
                if bf_to_use is not None:
                    cell.set("borderFillIDRef", str(bf_to_use))

                # Set character properties (font/size/color)
                cpr_to_use = header_charpr if is_header else data_charpr
                if cpr_to_use is not None:
                    for run in cell.findall(".//hp:run", NS):
                        run.set("charPrIDRef", str(cpr_to_use))

                # Set paragraph properties (align/spacing)
                ppr_to_use = header_parapr if is_header else data_parapr
                if ppr_to_use is not None:
                    for p in cell.findall(".//hp:p", NS):
                        p.set("paraPrIDRef", str(ppr_to_use))

                # Remove cached line break linesegarray to force recalculation
                for lsa in cell.findall(".//hp:linesegarray", NS):
                    cell.remove(lsa)

                changes += 1

        return changes

    def apply_table_format_file(
        self,
        src_hwpx: str,
        dst_hwpx: str,
        table_config: Dict[str, Any],
        section_name: str = "section0",
    ) -> int:
        """Formats tables in an HWPX file according to a configuration dict."""
        entries = unpack_hwpx(src_hwpx)
        sec_path = f"Contents/{section_name}.xml"
        if sec_path not in entries:
            raise KeyError(f"Section {sec_path} not found in HWPX archive.")

        root = ET.fromstring(entries[sec_path])
        tables = root.findall(".//hp:tbl", NS)

        target_indices = table_config.get("target_indices", list(range(len(tables))))
        col_widths = table_config.get("col_widths")
        total_width = table_config.get("total_width", sum(col_widths) if col_widths else None)
        hdr_charpr = table_config.get("header_charpr")
        data_charpr = table_config.get("data_charpr")
        hdr_bf = table_config.get("header_borderfill")
        data_bf = table_config.get("data_borderfill")
        hdr_ppr = table_config.get("header_parapr")
        data_ppr = table_config.get("data_parapr")

        total_changed = 0
        for ti in target_indices:
            if ti < len(tables):
                changed = self.format_table(
                    tables[ti],
                    col_widths=col_widths,
                    total_width=total_width,
                    header_charpr=hdr_charpr,
                    data_charpr=data_charpr,
                    header_borderfill=hdr_bf,
                    data_borderfill=data_bf,
                    header_parapr=hdr_ppr,
                    data_parapr=data_ppr,
                )
                total_changed += changed

        entries[sec_path] = ET.tostring(root, encoding="utf-8", xml_declaration=True)
        repack_hwpx(entries, dst_hwpx)
        return total_changed
