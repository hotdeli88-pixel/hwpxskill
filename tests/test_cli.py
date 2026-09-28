"""명령줄: 설치 없이 스킬 폴더의 scripts/hwpx.py 로 실행."""
import json
import os
import subprocess
import sys

from helpers import fixture, form_doc

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "skills", "hwpxskill", "scripts", "hwpx.py")


def run(*args, stdin=None):
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    p = subprocess.run([sys.executable, SCRIPT, *args], input=stdin, capture_output=True, text=True,
                       encoding="utf-8", env=env)
    return p.returncode, p.stdout, p.stderr


def test_version_and_help():
    code, out, _ = run("--version")
    assert code == 0 and "2." in out
    code, out, _ = run("--help")
    assert code == 0 and "fill" in out and "exam" in out


def test_analyze_json(tmp_path):
    code, out, _ = run("analyze", fixture("gian_general.hwpx"), "--json")
    assert code == 0
    rep = json.loads(out)
    assert rep["summary"]["fields"] >= 20
    assert any(f["name"] == "붙임" and "끝" in f["after"] for f in rep["fields"])


def test_fill_dry_run_then_save_with_check(tmp_path):
    out_path = tmp_path / "완성.hwpx"
    code, out, _ = run("fill", fixture("gian_general.hwpx"), "-d", fixture("gian_general_values.json"), "--dry-run")
    assert code == 0 and "미리보기" in out and not out_path.exists()
    code, out, _ = run("fill", fixture("gian_general.hwpx"), "-d", fixture("gian_general_values.json"),
                       "-o", str(out_path), "--render", "none", "--strict")
    assert code == 0, out
    assert out_path.exists() and "── 검수 ──" in out and "구조: 정상" in out


def test_fill_refuses_to_overwrite_source(tmp_path):
    src = tmp_path / "양식.hwpx"
    form_doc().save(str(src))
    data = tmp_path / "v.json"
    data.write_text(json.dumps({"values": {"기관명": "A"}}, ensure_ascii=False), encoding="utf-8")
    code, _, err = run("fill", str(src), "-d", str(data), "-o", str(src), "--no-check")
    assert code == 1 and "덮어쓰지" in err


def test_strict_exit_code_on_unmatched_key(tmp_path):
    src = tmp_path / "양식.hwpx"
    form_doc().save(str(src))
    code, out, _ = run("fill", str(src), "-d", "-", "--dry-run", "--strict",
                       stdin=json.dumps({"values": {"없는키": "x"}}, ensure_ascii=False))
    assert code == 2 and "없는키" in out


def test_lint_stdin_and_equation_check():
    code, out, _ = run("lint", "-", stdin="회의: 2026.9.28 오후 2시")
    assert code == 1 and "DATE_NO_SPACE" in out
    code, out, _ = run("equation", "check", "{a} over {b}", "\\frac{a}{b}")
    assert code == 1 and "[OK]" in out and "[오류]" in out


def test_exam_and_equation_roundtrip(tmp_path):
    data = tmp_path / "q.json"
    data.write_text(json.dumps({"questions": [{"text": "<eq>x^2 = 4</eq>의 해는?", "points": 2,
                                               "choices": ["1", "2", "3", "4", "5"]}]}, ensure_ascii=False),
                    encoding="utf-8")
    exam = tmp_path / "시험.hwpx"
    code, out, _ = run("exam", "-d", str(data), "-o", str(exam), "--render", "none")
    assert code == 0 and "구조: 정상" in out
    code, out, _ = run("equation", "list", str(exam), "--json")
    assert json.loads(out)[0]["script"] == "x^2 = 4"
    fixed = tmp_path / "고침.hwpx"
    code, out, _ = run("equation", "set", str(exam), "--find", "x^2=4", "--script", "x^2 = 9", "-o", str(fixed))
    assert code == 0 and fixed.exists()


def test_privacy_scan_and_validate(tmp_path):
    code, out, _ = run("validate", fixture("gian_simple.hwpx"))
    assert code == 0 and "정상" in out
    code, out, _ = run("privacy", "scan", fixture("gian_simple.hwpx"), "--json")
    assert code == 0 and isinstance(json.loads(out), list)
