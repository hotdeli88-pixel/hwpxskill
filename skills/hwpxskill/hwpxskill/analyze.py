"""양식 분석 — 채울 자리·표·예시 서식·수식을 한눈에 보는 보고서."""
from __future__ import annotations

from typing import Dict, List, Optional

from .core.model import Section
from .core.text import ParaText
from .equation import list_equations
from .forms import scan_document

HWPUNIT_PER_MM = 7200 / 25.4


def _mm(v: Optional[str]) -> Optional[float]:
    try:
        return round(int(v) / HWPUNIT_PER_MM, 1)
    except (TypeError, ValueError):
        return None


def page_info(doc) -> Dict:
    sec = Section(doc, 0)
    src = sec.src
    info: Dict = {}
    pp = next(sec.sec.iter("pagePr"), None)
    if pp is not None:
        info["width_mm"] = _mm(pp.get(src, "width"))
        info["height_mm"] = _mm(pp.get(src, "height"))
        info["landscape"] = pp.get(src, "landscape") == "NARROWLY"
        mg = pp.find("margin")
        if mg is not None:
            info["margin_mm"] = {k: _mm(mg.get(src, k)) for k in ("left", "right", "top", "bottom", "header", "footer")}
    cols = [int(c.get(src, "colCount") or 1) for c in sec.sec.iter("colPr")]
    info["columns"] = cols[0] if cols else 1
    if len(set(cols)) > 1:
        info["column_changes"] = cols
    return info


def analyze(doc, outline: bool = False, max_outline: int = 400) -> Dict:
    report: Dict = {"file": doc.path, "sections": len(doc.section_paths), "page": page_info(doc)}
    fields: List[Dict] = []
    placeholders: List[Dict] = []
    labels: List[Dict] = []
    rosters: List[Dict] = []
    inlines: List[Dict] = []
    checks: List[Dict] = []
    parens: List[Dict] = []
    empty_cells: List[Dict] = []
    examples: List[Dict] = []
    tables: List[Dict] = []
    for sec, scan in scan_document(doc):
        src = sec.src
        for f in scan.fields:
            fields.append({"name": f.name, "location": f.location, "guide": f.guide, "current": f.current,
                           "multi_paragraph": f.p_begin is not f.p_end,
                           "context": ParaText(src, f.p_begin).text[:60]})
        for ph in scan.placeholders:
            placeholders.append({"key": ph.key, "token": ph.token, "location": ph.location,
                                 "whole_paragraph": ph.whole_paragraph, "context": ph.context})
        for lb in scan.labels:
            labels.append({"label": lb.label, "key": lb.norm, "value_cell": lb.value_cell.address,
                           "current": lb.current[:60]})
        for r in scan.rosters:
            rosters.append({"table": r.table.id, "header_row": r.header_tr, "columns": [c[0] for c in r.columns],
                            "data_rows": len(r.data_trs), "empty_rows": r.empty_rows})
        for il in scan.inlines:
            inlines.append({"label": il.label, "ext_label": il.ext_label, "location": il.location,
                            "current": il.current[:40]})
        for pt in scan.patterns:
            item = {"label": pt.label, "location": pt.location, "context": pt.text[:60]}
            (checks if pt.kind == "checkbox" else parens).append(item)
        empty_cells.extend(scan.empty_cells)
        examples.extend(scan.example_cells)
        for t in sec.tables():
            grid = t.grid_text(src)
            tables.append({"id": t.id, "rows": t.row_count(src), "cols": t.col_count(src),
                           "in_cell": t.parent_cell, "preview": grid[:8]})
    report.update({
        "fields": fields, "placeholders": placeholders, "label_cells": labels, "rosters": rosters,
        "inline_labels": inlines, "checkboxes": checks, "paren_blanks": parens,
        "empty_cells": empty_cells[:200], "example_cells": examples, "tables": tables,
        "equations": list_equations(doc),
    })
    report["summary"] = {
        "fields": len(fields), "placeholders": len(placeholders), "label_cells": len(labels),
        "rosters": len(rosters), "inline_labels": len(inlines), "checkboxes": len(checks),
        "paren_blanks": len(parens), "empty_cells": len(empty_cells), "example_cells": len(examples),
        "tables": len(tables), "equations": len(report["equations"]),
    }
    if outline:
        report["outline"] = document_outline(doc, max_outline)
    return report


def document_outline(doc, limit: int = 400) -> List[str]:
    """본문 문단과 표를 주소와 함께 한 줄씩 (내용 파악용)."""
    out: List[str] = []
    for si in range(len(doc.section_paths)):
        sec = Section(doc, si)
        src = sec.src
        tables = {id(t.node): t for t in sec.tables()}
        for pi, p in enumerate(sec.paragraphs()):
            text = ParaText(src, p).text.strip()
            if text:
                out.append(f"s{si}.p{pi}: {text[:120]}")
            for tbl in p.iter("tbl"):
                t = tables.get(id(tbl))
                if t is None or t.parent_cell is not None:
                    continue
                out.append(f"  [표 {t.id} {t.row_count(src)}x{t.col_count(src)}]")
                for c in t.cells(src):
                    ct = c.text(src).strip().replace("\n", " / ")
                    if ct:
                        out.append(f"    {c.address}: {ct[:80]}")
            if len(out) >= limit:
                out.append("… (생략)")
                return out
    return out


def format_text(report: Dict) -> str:
    """사람이 읽는 요약."""
    L: List[str] = []
    s = report["summary"]
    pg = report.get("page", {})
    L.append(f"파일: {report.get('file')}")
    L.append(f"용지 {pg.get('width_mm')}×{pg.get('height_mm')}mm, 단 {pg.get('columns')}개, 섹션 {report['sections']}개")
    L.append("채울 자리: " + ", ".join(f"{k} {v}" for k, v in s.items() if v))
    if report["fields"]:
        L.append("\n[누름틀]")
        for f in report["fields"]:
            cur = f" (현재: {f['current'][:30]})" if f["current"] else ""
            L.append(f"  {f['name']} @ {f['location']} — 안내: {f['guide']}{cur}")
    if report["placeholders"]:
        L.append("\n[자리표시]")
        for p in report["placeholders"]:
            L.append(f"  {p['token']} @ {p['location']}{' (문단 전체)' if p['whole_paragraph'] else ''}")
    if report["label_cells"]:
        L.append("\n[표 라벨 → 값 칸]")
        for lb in report["label_cells"]:
            cur = f" (현재: {lb['current'][:30]})" if lb["current"].strip() else ""
            L.append(f"  {lb['label']} → {lb['value_cell']}{cur}")
    if report["rosters"]:
        L.append("\n[명단표]")
        for r in report["rosters"]:
            L.append(f"  {r['table']}: 머리행 {r['columns']} / 데이터 행 {r['data_rows']}개(빈 행 {r['empty_rows']})")
    if report["inline_labels"]:
        L.append("\n[본문 라벨]")
        for il in report["inline_labels"]:
            L.append(f"  {il['ext_label'] or il['label']}: @ {il['location']} (현재: {il['current']!r})")
    if report["checkboxes"] or report["paren_blanks"]:
        L.append("\n[체크박스·괄호 빈칸]")
        for c in report["checkboxes"]:
            L.append(f"  □{c['label']} @ {c['location']}")
        for c in report["paren_blanks"]:
            L.append(f"  {c['label']}(  ) @ {c['location']}")
    if report["example_cells"]:
        L.append("\n[예시가 채워진 셀 — 이 서식을 따라 씀]")
        for e in report["example_cells"]:
            L.append(f"  {e['cell']}: {e['text'][:80]!r}")
    if report["empty_cells"]:
        L.append(f"\n[그 밖의 빈 셀 {len(report['empty_cells'])}개 — cells 주소로 채움]")
        for e in report["empty_cells"][:30]:
            hint = e["left"] or e["above"]
            L.append(f"  {e['cell']}" + (f" (옆/위: {hint})" if hint else ""))
    if report["equations"]:
        L.append(f"\n[수식 {len(report['equations'])}개]")
        for q in report["equations"][:30]:
            L.append(f"  #{q['index']} @ {q['location']}: {q['script'][:60]}")
    if report["tables"]:
        L.append(f"\n[표 {len(report['tables'])}개]")
        for t in report["tables"][:20]:
            L.append(f"  {t['id']} {t['rows']}x{t['cols']}" + (f" (셀 {t['in_cell']} 안)" if t["in_cell"] else ""))
            for row in t["preview"][:4]:
                L.append("    | " + " | ".join(row) + " |")
    if report.get("outline"):
        L.append("\n[본문]")
        L.extend("  " + x for x in report["outline"])
    return "\n".join(L)
