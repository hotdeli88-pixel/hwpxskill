"""hwpxskill 명령줄.

    python scripts/hwpx.py <명령> ...      (스킬 폴더에서, 설치 없이)
    hwpxskill <명령> ...                    (pip 설치 후)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, List, Optional

from . import __version__
from .errors import HwpxError


def _utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            if (stream.encoding or "").lower().replace("-", "") != "utf8":
                stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass


def _load_json(path: str) -> Any:
    if path == "-":
        return json.load(sys.stdin)
    with open(path, encoding="utf-8-sig") as f:
        return json.load(f)


def _dump(obj: Any) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def _open(path: str):
    from .core.package import HwpxDocument
    return HwpxDocument.open(path)


def _default_out(src: str, suffix: str) -> str:
    stem, ext = os.path.splitext(src)
    return f"{stem}_{suffix}{ext if ext.lower() == '.hwpx' else '.hwpx'}"


# ── 명령 ──────────────────────────────────────────────────────────────────
def cmd_analyze(a) -> int:
    from .analyze import analyze, format_text
    rep = analyze(_open(a.file), outline=a.outline)
    if a.output:
        with open(a.output, "w", encoding="utf-8") as f:
            json.dump(rep, f, ensure_ascii=False, indent=2)
    if a.json:
        _dump(rep)
    else:
        print(format_text(rep))
        if a.output:
            print(f"\n(JSON 저장: {a.output})")
    return 0


def cmd_text(a) -> int:
    from .analyze import document_outline
    for line in document_outline(_open(a.file), a.limit):
        print(line)
    return 0


def cmd_fill(a) -> int:
    from .fill import fill_document
    doc = _open(a.file)
    data = _load_json(a.data)
    report = fill_document(doc, data)
    rep = report.to_dict()
    out = None
    if not a.dry_run:
        out = doc.save(a.output or _default_out(a.file, "완성"))
        rep["output"] = out
    if a.report:
        with open(a.report, "w", encoding="utf-8") as f:
            json.dump(rep, f, ensure_ascii=False, indent=2)
    if a.json:
        _dump(rep)
    else:
        _print_fill(rep, a.dry_run)
    if out and not a.no_check:
        print()
        _run_check(out, render=a.render, json_out=False)
    strict_bad = rep["skipped"] or rep["unmatched_keys"]
    return 2 if (a.strict and strict_bad) else 0


def _print_fill(rep: Dict, dry: bool) -> None:
    s = rep["summary"]
    head = "미리보기(저장 안 함)" if dry else "채우기 완료"
    print(f"{head}: {s['filled']}곳 채움, 건너뜀 {s['skipped']}, 행 추가 {s['rows_added']}, 안 쓰인 키 {s['unmatched_keys']}")
    for f in rep["filled"]:
        label = f.get("name") or f.get("token") or f.get("label") or f.get("column") or ""
        print(f"  [{f['kind']}] {f.get('location', '')} {label} ← {f.get('value', '')}")
    for r in rep["rows_added"]:
        print(f"  [행 추가] {r['table']}: {r['count']}행 (행 {r['template_row']} 서식 복제)")
    for sk in rep["skipped"]:
        print(f"  [건너뜀] {sk.get('location', '')} {sk.get('key', '')}: {sk.get('reason')}")
    if rep["unmatched_keys"]:
        print("  [안 쓰인 키] " + ", ".join(rep["unmatched_keys"]))
    for w in rep["warnings"]:
        print(f"  [경고] {w}")
    for n in rep["notes"]:
        print(f"  [참고] {n}")
    for e in rep.get("equations", []):
        print(f"  [수식 {e['index']}] {e['old']} → {e['new']}")
    if rep.get("output"):
        print(f"저장: {rep['output']}")


def cmd_equation(a) -> int:
    from .equation import check_script, estimate_size, list_equations, replace_equation
    if a.eq_cmd == "list":
        eqs = list_equations(_open(a.file))
        if a.json:
            _dump(eqs)
        else:
            if not eqs:
                print("수식이 없습니다")
            for q in eqs:
                print(f"#{q['index']} @ {q['location']} (크기 {q['baseUnit'] / 100:g}pt): {q['script']}")
        return 0
    if a.eq_cmd == "check":
        bad = False
        for s in a.scripts:
            fs = check_script(s)
            w, h, bl = estimate_size(s, int(a.pt * 100))
            status = "OK" if not fs else ("오류" if any(f.severity == "error" for f in fs) else "경고")
            print(f"[{status}] {s}  (추정 {w}x{h} HWPUNIT)")
            for f in fs:
                print(f"   - {f.severity}: {f.message}")
                bad = bad or f.severity == "error"
        return 1 if bad else 0
    if a.eq_cmd == "set":
        doc = _open(a.file)
        res = replace_equation(doc, a.index, a.script)
        out = doc.save(a.output or _default_out(a.file, "수식수정"))
        print(f"수식 {res['index']}: {res['old']} → {res['new']}\n저장: {out}")
        return 0
    return 1


def cmd_table_style(a) -> int:
    from .tablestyle import apply_table_style
    doc = _open(a.file)
    src_doc = _open(a.source) if a.source else None
    rep = apply_table_style(doc, a.to, a.from_table, source_doc=src_doc, widths=not a.keep_widths)
    out = doc.save(a.output or _default_out(a.file, "표스타일"))
    if a.json:
        _dump({**rep, "output": out})
    else:
        print(f"표 스타일 복제: {a.from_table} → {', '.join(a.to)}")
        for line in rep.get("log", []):
            print(f"  {line}")
        print(f"저장: {out}")
    return 0


def cmd_exam(a) -> int:
    from .exam import build_exam
    data = _load_json(a.data)
    out, rep = build_exam(data, template=a.template, output=a.output)
    if a.json:
        _dump({**rep, "output": out})
    else:
        print(f"시험지 {rep.get('mode')}: 문항 {rep.get('questions')}개, 단 {rep.get('columns')}개")
        for n in rep.get("notes", []):
            print(f"  [참고] {n}")
        print(f"저장: {out}")
    if not a.no_check:
        print()
        _run_check(out, render=a.render, json_out=False)
    return 0


def cmd_lint(a) -> int:
    from .lint import lint_document, lint_text, format_findings
    if a.file and (a.file.lower().endswith(".hwpx")):
        findings = lint_document(_open(a.file), munche=a.munche)
    else:
        if a.file and a.file != "-":
            if a.file.lower().endswith(".json"):
                data = _load_json(a.file)
                text = "\n".join(_json_strings(data))
            else:
                with open(a.file, encoding="utf-8") as f:
                    text = f.read()
        else:
            text = sys.stdin.read()
        findings = lint_text(text, munche=a.munche, document=True)
    if a.json:
        _dump(findings)
    else:
        print(format_findings(findings))
    return 1 if any(f["severity"] == "error" for f in findings) else 0


def _json_strings(obj: Any) -> List[str]:
    out: List[str] = []
    if isinstance(obj, str):
        out.append(obj)
    elif isinstance(obj, dict):
        for k, v in obj.items():
            if k in ("options", "format"):
                continue
            out.extend(_json_strings(v))
    elif isinstance(obj, list):
        for v in obj:
            out.extend(_json_strings(v))
    return out


def cmd_privacy(a) -> int:
    from .privacy import scan_document, redact_document, format_findings
    doc = _open(a.file)
    if a.priv_cmd == "scan":
        findings = scan_document(doc, rules=a.rules)
        if a.json:
            _dump(findings)
        else:
            print(format_findings(findings))
        return 0
    rep = redact_document(doc, rules=a.rules)
    out = doc.save(a.output or _default_out(a.file, "가림"))
    print(f"가림 {rep['masked']}건 → 저장: {out}")
    left = scan_document(_open(out), rules=a.rules)
    left = [f for f in left if f["level"] != "info"]
    if left:
        print(f"  [경고] 가린 뒤에도 {len(left)}건이 남았습니다 — 직접 확인하세요")
        return 2
    return 0


def cmd_validate(a) -> int:
    from .validate import validate, format_result
    res = validate(_open(a.file))
    if a.json:
        _dump(res)
    else:
        print(format_result(res))
    return 0 if res["ok"] else 1


def _run_check(path: str, render: str, json_out: bool) -> Dict:
    from .validate import validate, format_result
    from .privacy import scan_document, format_findings
    from .lint import lint_document
    doc = _open(path)
    res = {"file": path, "validate": validate(doc)}
    res["privacy"] = scan_document(doc)
    res["lint"] = lint_document(doc)
    if render != "none":
        from .render import render_pdf
        res["render"] = render_pdf(path, engine=render)
    if json_out:
        _dump(res)
    else:
        print("── 검수 ──")
        print(format_result(res["validate"]))
        pv = [f for f in res["privacy"] if f["level"] != "info"]
        if pv:
            print(format_findings(res["privacy"]))
        else:
            print("개인정보: 경고 없음" + (f" (공개 연락처 {len(res['privacy'])}건은 허용)" if res["privacy"] else ""))
        errs = [f for f in res["lint"] if f["severity"] == "error"]
        print(f"표기법: 오류 {len(errs)}건, 경고 {len(res['lint']) - len(errs)}건" + (" (자세히: lint 명령)" if res["lint"] else ""))
        if "render" in res:
            r = res["render"]
            if r.get("ok"):
                print(f"렌더: {r['engine']} → {r['pdf']}  ← 이 PDF를 열어 페이지를 확인하세요")
            else:
                print(f"렌더: 건너뜀 — {r.get('reason')}")
    return res


def cmd_check(a) -> int:
    res = _run_check(a.file, render=a.render, json_out=a.json)
    return 0 if res["validate"]["ok"] else 1


def cmd_render(a) -> int:
    from .render import render_pdf
    res = render_pdf(a.file, output=a.output, engine=a.engine)
    if a.json:
        _dump(res)
    elif res.get("ok"):
        print(f"PDF: {res['pdf']} ({res['engine']})")
    else:
        print(f"렌더 실패: {res.get('reason')}")
    return 0 if res.get("ok") else 1


def cmd_convert(a) -> int:
    from .render import convert
    res = convert(a.file, output=a.output, to=a.to, engine=a.engine)
    if res.get("ok"):
        print(f"변환: {res['output']} ({res['engine']})")
        return 0
    print(f"변환 실패: {res.get('reason')}")
    return 1


def cmd_doctor(a) -> int:
    from .render import doctor
    info = doctor()
    if a.json:
        _dump(info)
    else:
        print(f"hwpxskill {__version__} / Python {info['python']} / {info['os']}")
        print(f"  한글(Windows 자동화): {'사용 가능' if info['hancom'] else '없음'} {info.get('hancom_note', '')}")
        print(f"  rhwp: {info['rhwp'] or '없음'}")
        print(f"  PDF 렌더 가능: {'예 (' + info['render_engine'] + ')' if info['render_engine'] else '아니요 — references/setup.md 참고'}")
    return 0


# ── 파서 ──────────────────────────────────────────────────────────────────
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="hwpxskill", description="HWPX 양식 채우기·편집 엔진")
    p.add_argument("--version", action="version", version=f"hwpxskill {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("analyze", help="양식에서 채울 자리·표·예시 서식·수식 찾기")
    s.add_argument("file")
    s.add_argument("--json", action="store_true")
    s.add_argument("--outline", action="store_true", help="본문 문단·표 내용도 함께")
    s.add_argument("-o", "--output", help="JSON 보고서 저장 경로")
    s.set_defaults(func=cmd_analyze)

    s = sub.add_parser("text", help="문서 글을 주소와 함께 보기")
    s.add_argument("file")
    s.add_argument("--limit", type=int, default=1000)
    s.set_defaults(func=cmd_text)

    s = sub.add_parser("fill", help="값 JSON으로 양식 채우기")
    s.add_argument("file")
    s.add_argument("-d", "--data", required=True, help="채울 값 JSON (- 는 표준입력)")
    s.add_argument("-o", "--output", help="저장 경로 (기본: 원본이름_완성.hwpx)")
    s.add_argument("--dry-run", action="store_true", help="저장하지 않고 어디에 무엇이 들어갈지만 보기")
    s.add_argument("--report", help="채우기 결과 JSON 저장 경로")
    s.add_argument("--json", action="store_true")
    s.add_argument("--no-check", action="store_true", help="저장 후 검수 생략")
    s.add_argument("--render", default="auto", choices=["auto", "hancom", "rhwp", "none"], help="검수 때 PDF 렌더 엔진")
    s.add_argument("--strict", action="store_true", help="건너뜀·안 쓰인 키가 있으면 종료 코드 2")
    s.set_defaults(func=cmd_fill)

    s = sub.add_parser("equation", help="수식 목록·검사·수정 (한글 수식 스크립트)")
    esub = s.add_subparsers(dest="eq_cmd", required=True)
    e = esub.add_parser("list")
    e.add_argument("file")
    e.add_argument("--json", action="store_true")
    e = esub.add_parser("check", help="스크립트 문법 검사")
    e.add_argument("scripts", nargs="+")
    e.add_argument("--pt", type=float, default=10.0)
    e = esub.add_parser("set", help="index번째 수식 바꾸기")
    e.add_argument("file")
    e.add_argument("--index", type=int, required=True)
    e.add_argument("--script", required=True)
    e.add_argument("-o", "--output")
    s.set_defaults(func=cmd_equation)

    s = sub.add_parser("table-style", help="다른 표(다른 문서 가능)의 스타일을 표에 입히기")
    s.add_argument("file", help="고칠 문서")
    s.add_argument("--from", dest="from_table", required=True, help="원본 표 주소 (예: s0.t0)")
    s.add_argument("--source", help="원본 표가 있는 다른 문서 (없으면 같은 문서)")
    s.add_argument("--to", nargs="+", required=True, help="대상 표 주소들")
    s.add_argument("--keep-widths", action="store_true", help="대상 표의 열 너비는 그대로")
    s.add_argument("-o", "--output")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_table_style)

    s = sub.add_parser("exam", help="시험지·학습지 만들기 (양식 채우기 또는 새로 만들기)")
    s.add_argument("-d", "--data", required=True, help="문항 JSON")
    s.add_argument("-t", "--template", help="시험지 양식 HWPX (없으면 내장 2단 시험지)")
    s.add_argument("-o", "--output", required=True)
    s.add_argument("--json", action="store_true")
    s.add_argument("--no-check", action="store_true")
    s.add_argument("--render", default="auto", choices=["auto", "hancom", "rhwp", "none"])
    s.set_defaults(func=cmd_exam)

    s = sub.add_parser("lint", help="공문서 표기법(+개조식 문체) 검사: .hwpx, .txt, 값 JSON, 표준입력")
    s.add_argument("file", nargs="?", default="-")
    s.add_argument("--munche", action="store_true", help="개조식 문체 규칙도 검사")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_lint)

    s = sub.add_parser("privacy", help="개인정보 검사(scan) / 가린 사본 만들기(redact)")
    psub = s.add_subparsers(dest="priv_cmd", required=True)
    for name in ("scan", "redact"):
        e = psub.add_parser(name)
        e.add_argument("file")
        e.add_argument("--rules", help="쉼표 목록 (기본: rrn,foreigner,phone,email,card,account,passport,driver)")
        e.add_argument("--json", action="store_true")
        if name == "redact":
            e.add_argument("-o", "--output")
    s.set_defaults(func=cmd_privacy)

    s = sub.add_parser("validate", help="HWPX 구조 검사")
    s.add_argument("file")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_validate)

    s = sub.add_parser("check", help="검수: 구조 + 개인정보 + 표기법 + PDF 렌더")
    s.add_argument("file")
    s.add_argument("--render", default="auto", choices=["auto", "hancom", "rhwp", "none"])
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_check)

    s = sub.add_parser("render", help="PDF로 렌더 (Windows 한글 / rhwp)")
    s.add_argument("file")
    s.add_argument("-o", "--output")
    s.add_argument("--engine", default="auto", choices=["auto", "hancom", "rhwp"])
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_render)

    s = sub.add_parser("convert", help="HWP → HWPX 변환 (또는 --to hwp)")
    s.add_argument("file")
    s.add_argument("-o", "--output")
    s.add_argument("--to", default="hwpx", choices=["hwpx", "hwp", "pdf"])
    s.add_argument("--engine", default="auto", choices=["auto", "hancom", "rhwp"])
    s.set_defaults(func=cmd_convert)

    s = sub.add_parser("doctor", help="실행 환경 점검 (한글 자동화·rhwp)")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_doctor)
    return p


def main(argv: Optional[List[str]] = None) -> int:
    _utf8_stdio()
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args) or 0)
    except HwpxError as e:
        print(f"오류: {e}", file=sys.stderr)
        return 1
    except BrokenPipeError:  # `| head` 등으로 출력이 끊긴 경우
        try:
            sys.stdout = open(os.devnull, "w")
        except OSError:
            pass
        return 0
    except FileNotFoundError as e:
        print(f"오류: 파일을 찾을 수 없습니다 — {e.filename}", file=sys.stderr)
        return 1
    except json.JSONDecodeError as e:
        print(f"오류: JSON 형식이 올바르지 않습니다 — {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
