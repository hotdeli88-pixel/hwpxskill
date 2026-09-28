"""PDF 렌더와 형식 변환 — Windows는 한글(COM 자동화), Mac·Linux는 rhwp.

- 한글: pywin32로 `HWPFrame.HwpObject`를 열어 SaveAs(PDF/HWPX/HWP). 보안 승인 창을 피하려면
  한컴 '보안 모듈(FilePathCheckerModule)'을 등록해 두어야 한다 (references/setup.md).
- rhwp: `rhwp export-pdf 입력 -o 출력.pdf`, `rhwp export-hwpx 입력.hwp 출력.hwpx`,
  `rhwp convert 입력.hwpx 출력.hwp`. PATH 또는 환경변수 HWPXSKILL_RHWP 로 찾는다.
"""
from __future__ import annotations

import functools
import os
import platform
import shutil
import subprocess
import sys
from typing import Dict, List, Optional

_RHWP_CANDIDATES = [
    "~/.cargo/bin/rhwp", "~/.local/bin/rhwp", "/opt/homebrew/bin/rhwp", "/usr/local/bin/rhwp",
    "~/bin/rhwp", "~/rhwp/rhwp",
]


def find_rhwp() -> Optional[str]:
    env = os.environ.get("HWPXSKILL_RHWP")
    if env and os.path.exists(os.path.expanduser(env)):
        return os.path.expanduser(env)
    p = shutil.which("rhwp")
    if p:
        return p
    for c in _RHWP_CANDIDATES:
        c = os.path.expanduser(c)
        if os.path.exists(c):
            return c
    return None


def rhwp_version(path: str) -> Optional[str]:
    try:
        out = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=20)
        return (out.stdout or out.stderr).strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def hancom_available() -> bool:
    if platform.system() != "Windows":
        return False
    try:
        import win32com.client  # type: ignore  # noqa: F401
        import winreg  # type: ignore
        winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, "HWPFrame.HwpObject")
        return True
    except Exception:
        return False


class _Hancom:
    """한글 COM 세션 (with 문으로 사용)."""

    def __enter__(self):
        import win32com.client as win32  # type: ignore
        self.hwp = win32.Dispatch("HWPFrame.HwpObject")
        try:
            self.hwp.XHwpWindows.Item(0).Visible = False
        except Exception:
            pass
        for mod in ("FilePathCheckerModule", "FilePathCheckerModuleExample", "SecurityModule"):
            try:
                if self.hwp.RegisterModule("FilePathCheckDLL", mod):
                    break
            except Exception:
                continue
        try:
            self.hwp.SetMessageBoxMode(0x00011011)  # 확인·예 자동 선택
        except Exception:
            pass
        return self.hwp

    def __exit__(self, *exc):
        try:
            self.hwp.Clear(1)
            self.hwp.Quit()
        except Exception:
            pass


def _fmt_of(path: str) -> str:
    return "HWPX" if path.lower().endswith(".hwpx") else "HWP" if path.lower().endswith(".hwp") else ""


def _hancom_save_as(src: str, dst: str, fmt: str) -> Dict:
    src, dst = os.path.abspath(src), os.path.abspath(dst)
    with _Hancom() as hwp:
        if not hwp.Open(src, _fmt_of(src), "forceopen:true;versionwarning:false"):
            return {"ok": False, "engine": "hancom", "reason": "한글이 파일을 열지 못했습니다 (파일 손상 가능)"}
        pages = None
        try:
            pages = int(hwp.PageCount)
        except Exception:
            pass
        ok = hwp.SaveAs(dst, fmt, "")
    if not ok or not os.path.exists(dst):
        return {"ok": False, "engine": "hancom", "reason": f"한글 {fmt} 저장 실패"}
    return {"ok": True, "engine": "hancom", "output": dst, "pages": pages}


def _run_rhwp(args: List[str]) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True, timeout=600)


_FONT_DIRS = ["~/Library/Fonts", "/Library/Fonts", "/System/Library/Fonts", "/usr/share/fonts",
              "/usr/local/share/fonts", "~/.fonts", "~/.local/share/fonts", "C:/Windows/Fonts"]


@functools.lru_cache(maxsize=None)
def _installed_fonts() -> str:
    """설치된 글꼴 이름·파일 이름을 소문자로 이어 붙인 문자열 (있는지 대충 볼 때만 씀)."""
    names: List[str] = []
    if shutil.which("fc-list"):
        try:
            names.append(subprocess.run(["fc-list", ":", "family", "file"], capture_output=True, text=True,
                                        timeout=30).stdout)
        except (OSError, subprocess.SubprocessError):
            pass
    extra = [d for d in os.environ.get("HWPXSKILL_FONT_PATH", "").split(os.pathsep) if d]
    for d in _FONT_DIRS + extra:
        d = os.path.expanduser(d)
        for root, _dirs, files in os.walk(d) if os.path.isdir(d) else ():
            names.extend(files)
            if root.count(os.sep) - d.count(os.sep) >= 3:
                _dirs[:] = []
    return "\n".join(names).lower()


def _rhwp_pdf_font_args() -> List[str]:
    """rhwp PDF 글꼴 옵션: HWPXSKILL_FONT_PATH 폴더들, 수식 글꼴(HYhwpEQ)이 없으면 대체 글꼴.

    수식 글꼴이 없으면 rhwp가 수식을 빈 네모로 그릴 수 있어 검수 PDF를 잘못 읽게 된다."""
    args: List[str] = []
    for d in os.environ.get("HWPXSKILL_FONT_PATH", "").split(os.pathsep):
        if d and os.path.isdir(os.path.expanduser(d)):
            args += ["--font-path", os.path.expanduser(d)]
    eq = os.environ.get("HWPXSKILL_EQ_FONT")
    fonts = _installed_fonts()
    if not eq and "hyhwpeq" not in fonts:
        for fam in ("Times New Roman", "Noto Serif KR", "Noto Serif CJK KR", "Nanum Myeongjo", "DejaVu Serif",
                    "Liberation Serif"):
            if fam.lower() in fonts or fam.lower().replace(" ", "") in fonts:
                eq = fam
                break
    if eq:
        args += ["--equation-font", eq]
    return args


def _choose(engine: str) -> Optional[str]:
    if engine in ("auto", "hancom") and hancom_available():
        return "hancom"
    if engine in ("auto", "rhwp") and find_rhwp():
        return "rhwp"
    return None


def render_pdf(path: str, output: Optional[str] = None, engine: str = "auto") -> Dict:
    """HWPX/HWP → PDF. 결과 dict: ok, engine, pdf, reason."""
    out = output or os.path.splitext(path)[0] + ".pdf"
    eng = _choose(engine)
    if eng is None:
        return {"ok": False, "reason": _no_engine_msg()}
    if eng == "hancom":
        try:
            res = _hancom_save_as(path, out, "PDF")
        except Exception as e:  # COM 오류
            res = {"ok": False, "engine": "hancom", "reason": f"한글 자동화 오류: {e}"}
        if res.get("ok"):
            res["pdf"] = res.pop("output")
            return res
        if engine == "auto" and find_rhwp():
            eng = "rhwp"
        else:
            return res
    rhwp = find_rhwp()
    p = _run_rhwp([rhwp, "export-pdf", path, "-o", out] + _rhwp_pdf_font_args())
    if p.returncode != 0 or not os.path.exists(out):
        return {"ok": False, "engine": "rhwp", "reason": (p.stderr or p.stdout).strip()[:500] or "rhwp 실패"}
    return {"ok": True, "engine": "rhwp", "pdf": out}


def convert(path: str, output: Optional[str] = None, to: str = "hwpx", engine: str = "auto") -> Dict:
    """HWP → HWPX (기본), HWPX → HWP, → PDF. 원본은 건드리지 않는다."""
    to = to.lower()
    out = output or os.path.splitext(path)[0] + "." + to
    if os.path.abspath(out) == os.path.abspath(path):
        return {"ok": False, "reason": "출력 경로가 원본과 같습니다"}
    if to == "pdf":
        r = render_pdf(path, out, engine)
        if r.get("ok"):
            r["output"] = r["pdf"]
        return r
    eng = _choose(engine)
    if eng is None:
        return {"ok": False, "reason": _no_engine_msg()}
    if eng == "hancom":
        try:
            return _hancom_save_as(path, out, to.upper())
        except Exception as e:
            if not find_rhwp():
                return {"ok": False, "engine": "hancom", "reason": f"한글 자동화 오류: {e}"}
    rhwp = find_rhwp()
    args = [rhwp, "export-hwpx", path, out] if to == "hwpx" else [rhwp, "convert", path, out]
    p = _run_rhwp(args)
    if p.returncode != 0 or not os.path.exists(out):
        return {"ok": False, "engine": "rhwp", "reason": (p.stderr or p.stdout).strip()[:500] or "rhwp 실패"}
    return {"ok": True, "engine": "rhwp", "output": out}


_CFB_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"


def is_hwp_binary(path: str) -> bool:
    """HWP 5.x(복합 파일) 또는 HWP 3.x 인지."""
    try:
        with open(path, "rb") as f:
            head = f.read(32)
    except OSError:
        return False
    return head.startswith(_CFB_MAGIC) or head.startswith(b"HWP Document File")


def ensure_hwpx(path: str, engine: str = "auto", log=None) -> str:
    """HWP면 옆에 HWPX로 바꿔 두고 그 경로를 돌려준다 (원본은 그대로). HWPX면 그대로.

    `이름.hwpx`가 없으면 거기에, 있으면서 원본보다 새로우면 그 변환본을 다시 쓰고,
    원본보다 오래됐으면 `이름_변환.hwpx`에 만든다 (사용자가 만든 파일을 덮어쓰지 않음)."""
    if not is_hwp_binary(path):
        return path
    from .errors import HwpxError
    say = log or (lambda m: print(m, file=sys.stderr))
    stem = os.path.splitext(path)[0]
    target = stem + ".hwpx"
    if os.path.exists(target):
        if os.path.getmtime(target) >= os.path.getmtime(path) and not is_hwp_binary(target):
            say(f"[변환] 이미 변환된 파일을 씁니다: {target}")
            return target
        target = stem + "_변환.hwpx"
    r = convert(path, target, "hwpx", engine)
    if not r.get("ok"):
        raise HwpxError(f"HWP → HWPX 변환 실패: {r.get('reason')}")
    say(f"[변환] HWP → HWPX ({r.get('engine')}): {r['output']}")
    return r["output"]


def _no_engine_msg() -> str:
    if platform.system() == "Windows":
        return "한글 자동화(pywin32 + 한글)와 rhwp를 찾지 못했습니다 — references/setup.md의 Windows 설정을 보세요"
    return "rhwp를 찾지 못했습니다 — references/setup.md의 rhwp 설치를 보세요 (또는 HWPXSKILL_RHWP 환경변수)"


def doctor() -> Dict:
    rh = find_rhwp()
    info = {
        "python": sys.version.split()[0],
        "os": f"{platform.system()} {platform.release()}",
        "hancom": hancom_available(),
        "rhwp": f"{rh} ({rhwp_version(rh) or '?'})" if rh else None,
    }
    if platform.system() == "Windows" and not info["hancom"]:
        try:
            import win32com.client  # type: ignore  # noqa: F401
            info["hancom_note"] = "(pywin32는 있으나 한글 COM 등록을 찾지 못함)"
        except Exception:
            info["hancom_note"] = "(pip install pywin32 필요)"
    info["render_engine"] = "hancom" if info["hancom"] else ("rhwp" if rh else None)
    if rh:
        eq = [a for a in _rhwp_pdf_font_args() if not a.startswith("--")]
        info["equation_font"] = "HYhwpEQ" if "hyhwpeq" in _installed_fonts() else (
            f"대체 글꼴 {eq[-1]}" if eq else "없음 — 수식이 빈 네모로 보일 수 있음 (HWPXSKILL_EQ_FONT 설정)")
    return info
