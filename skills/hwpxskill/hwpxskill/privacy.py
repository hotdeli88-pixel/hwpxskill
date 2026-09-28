"""개인정보 검사·가리기.

- 본문 글자(hp:t)만 검사한다. XML 속성·태그 숫자는 보지 않는다.
- 결과는 경고용이다 (결과 파일을 막지 않음). level: warning(개인정보) / info(공개 연락처로 보이는 것).
- 기관 대표번호(지역번호·1588 등)와 기관 도메인 이메일(go.kr·korea.kr·ac.kr 등)은 info로 둔다.
- redact는 서식을 유지한 채 글자만 가린 사본을 만든다 (미리보기 글·그림도 정리).
검증 규칙(주민번호 생년월일, 카드 Luhn, 사업자번호 체크섬, 라벨 문맥)은 kordoc(MIT) redact-rules.ts를 참고했다.
"""
from __future__ import annotations

import datetime
import re
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from .core.model import Section
from .core.text import ParaText, inline_xml

DEFAULT_RULES = ("rrn", "foreigner", "phone", "email", "card", "account", "passport", "driver")
_PERSONAL_MAIL = ("gmail.", "naver.", "daum.", "hanmail.", "kakao.", "nate.", "hotmail.", "outlook.", "yahoo.",
                  "icloud.", "live.", "me.com", "proton")
_PUBLIC_MAIL = (".go.kr", "korea.kr", ".ac.kr", ".or.kr", ".re.kr", ".es.kr", ".ms.kr", ".hs.kr", ".sc.kr",
                ".kr")
_LABEL = {
    "account": re.compile(r"계\s*좌|예\s*금\s*주|입\s*금|은\s*행|농\s*협|신\s*협|수\s*협|우\s*체\s*국|금\s*고|account", re.I),
    "passport": re.compile(r"여\s*권|passport", re.I),
    "driver": re.compile(r"운\s*전\s*면\s*허|면\s*허\s*번\s*호|licen[cs]e", re.I),
    "phone_public": re.compile(r"대\s*표|문\s*의|팩\s*스|fax|콜\s*센\s*터|상\s*담|민\s*원|담\s*당|교\s*무\s*실|행\s*정\s*실|전\s*화|☎|tel", re.I),
    "other": re.compile(r"접\s*수\s*번\s*호|문\s*서\s*번\s*호|과\s*제\s*번\s*호|사\s*업\s*번\s*호|ISBN|ISSN|일\s*련\s*번\s*호|코\s*드|모\s*델|시\s*리\s*얼|serial", re.I),
}


def _birth_ok(front6: str, g: str) -> bool:
    try:
        yy, mm, dd = int(front6[:2]), int(front6[2:4]), int(front6[4:6])
    except ValueError:
        return False
    if not 1 <= mm <= 12 or dd < 1:
        return False
    year = (2000 if g in "3478" else 1900) + yy
    if year > datetime.date.today().year:
        return False
    try:
        datetime.date(year, mm, dd)
    except ValueError:
        return False
    return True


def _luhn(d: str) -> bool:
    s = 0
    for i, ch in enumerate(reversed(d)):
        n = ord(ch) - 48
        if i % 2:
            n *= 2
            if n > 9:
                n -= 9
        s += n
    return s % 10 == 0


def _same_digits(d: str) -> bool:
    return bool(d) and len(set(d)) == 1


# (규칙, 정규식, 판정 → level 또는 None)
Detector = Tuple[str, "re.Pattern[str]", Callable[["re.Match[str]", str], Optional[str]]]


def _rrn(m: "re.Match[str]", ctx: str) -> Optional[str]:
    front, g, back = m.group(1), m.group(2), m.group(3)
    if _same_digits(front + g + back) or "*" in m.group(0):
        return None
    if g in "1234" and _birth_ok(front, g):
        return "warning"
    return None


def _foreigner(m: "re.Match[str]", ctx: str) -> Optional[str]:
    front, g = m.group(1), m.group(2)
    return "warning" if g in "5678" and _birth_ok(front, g) else None


def _phone(m: "re.Match[str]", ctx: str) -> Optional[str]:
    d = re.sub(r"\D", "", m.group(0))
    if _same_digits(d[3:]) or re.search(r"0{4}$", d) and d.startswith("01"):
        return None
    if _LABEL["other"].search(ctx):
        return None
    if d.startswith("01"):
        return "warning"
    return "info"


def _email(m: "re.Match[str]", ctx: str) -> Optional[str]:
    dom = m.group(2).lower()
    if any(p in dom for p in _PERSONAL_MAIL):
        return "warning"
    if dom.endswith(_PUBLIC_MAIL) or "example" in dom:
        return "info"
    return "warning"


def _card(m: "re.Match[str]", ctx: str) -> Optional[str]:
    d = re.sub(r"\D", "", m.group(0))
    return "warning" if 13 <= len(d) <= 19 and _luhn(d) and not _same_digits(d) else None


def _labeled(kind: str) -> Callable[["re.Match[str]", str], Optional[str]]:
    def f(m: "re.Match[str]", ctx: str) -> Optional[str]:
        d = re.sub(r"\D", "", m.group(0))
        if _same_digits(d):
            return None
        return "warning" if _LABEL[kind].search(ctx) else None
    return f


DETECTORS: List[Detector] = [
    ("email", re.compile(r"([A-Za-z0-9._%+-]+)@([A-Za-z0-9.-]+\.[A-Za-z]{2,})"), _email),
    ("rrn", re.compile(r"(?<![\d-])(\d{6})\s?[-–]\s?([1-4])(\d{6})(?!\d)"), _rrn),
    ("foreigner", re.compile(r"(?<![\d-])(\d{6})\s?[-–]\s?([5-8])(\d{6})(?!\d)"), _foreigner),
    ("card", re.compile(r"(?<!\d)\d{4}[-\s]\d{4}[-\s]\d{4}[-\s]\d{1,7}(?!\d)"), _card),
    ("driver", re.compile(r"(?<!\d)\d{2}-\d{2}-\d{6}-\d{2}(?!\d)"), _labeled("driver")),
    ("phone", re.compile(r"(?<![\d-])(?:01[016789]|0(?:2|[3-6][1-5]|70|50\d))[-.)\s]?\d{3,4}[-.\s]?\d{4}(?![\d-])"
                         r"|(?<![\d-])1[5-9]\d{2}-\d{4}(?![\d-])"), _phone),
    ("passport", re.compile(r"(?<![A-Za-z0-9])[A-Z]{1,2}\d{7,8}(?![A-Za-z0-9])"), _labeled("passport")),
    ("account", re.compile(r"(?<![\d-])\d{2,6}(?:-\d{2,6}){2,4}(?![\d-])|(?<!\d)\d{11,14}(?!\d)"), _labeled("account")),
]


def _rules(rules: Optional[str]) -> Sequence[str]:
    if not rules:
        return DEFAULT_RULES
    return [r.strip() for r in rules.split(",") if r.strip()]


def scan_text(text: str, rules: Sequence[str] = DEFAULT_RULES) -> List[Dict]:
    out: List[Dict] = []
    taken: List[Tuple[int, int]] = []
    for rule, pat, judge in DETECTORS:
        if rule not in rules:
            continue
        for m in pat.finditer(text):
            if any(not (m.end() <= a or m.start() >= b) for a, b in taken):
                continue
            ctx = text[max(0, m.start() - 40):m.start()]
            prev = list(re.finditer(r"\d[\d\-.\s]{4,}\d", ctx))
            if prev:  # 앞선 값 뒤부터만 문맥으로 본다 (앞 값의 라벨이 번지지 않게)
                ctx = ctx[prev[-1].end():]
            if rule in ("account", "passport", "driver") and _LABEL["other"].search(ctx):
                continue
            level = judge(m, ctx)
            if level is None:
                continue
            taken.append((m.start(), m.end()))
            out.append({"rule": rule, "level": level, "start": m.start(), "end": m.end(), "match": m.group(0)})
    return sorted(out, key=lambda x: x["start"])


def _mask(rule: str, s: str) -> str:
    if rule in ("rrn", "foreigner"):
        m = re.match(r"(\d{6}\s?[-–]\s?\d)(\d{6})", s)
        return m.group(1) + "*" * 6 if m else re.sub(r"\d", "*", s)
    if rule == "phone":
        parts = re.split(r"([-.)\s])", s)
        if len(parts) >= 5:
            parts[2] = "*" * len(parts[2])
            return "".join(parts)
        d = re.sub(r"\D", "", s)
        return s[:3] + re.sub(r"\d", "*", s[3:-4]) + s[-4:] if len(d) >= 9 else re.sub(r"\d", "*", s)
    if rule == "email":
        local, _, dom = s.partition("@")
        return (local[:1] + "*" * max(len(local) - 1, 2)) + "@" + dom
    if rule == "card":
        return re.sub(r"\d", "*", s[:-4]) + s[-4:]
    return re.sub(r"[0-9A-Za-z]", "*", s)


def _where(sec: Section, p) -> str:
    return sec.paragraph_address(p)


def scan_document(doc, rules: Optional[str] = None) -> List[Dict]:
    rs = _rules(rules)
    out: List[Dict] = []
    for si in range(len(doc.section_paths)):
        sec = Section(doc, si)
        for p in sec.iter_paragraphs():
            t = ParaText(sec.src, p).text
            if not t or not re.search(r"\d|@", t):
                continue
            for f in scan_text(t, rs):
                f["location"] = _where(sec, p)
                f["context"] = t[max(0, f["start"] - 12):f["end"] + 12]
                out.append(f)
    return out


def redact_document(doc, rules: Optional[str] = None, include_info: bool = False) -> Dict:
    """개인정보(warning)를 가린다. include_info=True면 공개 연락처(info)도 가린다."""
    rs = _rules(rules)
    masked = 0
    for si in range(len(doc.section_paths)):
        sec = Section(doc, si)
        splices = []
        for p in sec.iter_paragraphs():
            pt = ParaText(sec.src, p)
            if not re.search(r"\d|@", pt.text):
                continue
            for f in scan_text(pt.text, rs):
                if f["level"] == "info" and not include_info:
                    continue
                splices.extend(pt.replace(f["start"], f["end"], inline_xml(_mask(f["rule"], f["match"]), sec.hp)))
                masked += 1
        doc.apply(sec.path, splices, layout_changed=False)
    # 미리보기 글·그림
    if "Preview/PrvText.txt" in doc.archive.names():
        from .core.package import preview_text
        doc.set_text("Preview/PrvText.txt", preview_text(doc), layout_changed=False)
    if "Preview/PrvImage.png" in doc.archive.names():
        doc.set_binary("Preview/PrvImage.png", _BLANK_PNG)
    return {"masked": masked}


_BLANK_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010802000000907753de0000000c49444154789c63f8ffff3f"
    "0005fe02fe0def46b80000000049454e44ae426082")


def format_findings(findings: List[Dict]) -> str:
    warn = [f for f in findings if f["level"] != "info"]
    info = [f for f in findings if f["level"] == "info"]
    lines = [f"개인정보: 경고 {len(warn)}건" + (f", 공개 연락처(허용) {len(info)}건" if info else "")]
    names = {"rrn": "주민등록번호", "foreigner": "외국인등록번호", "phone": "전화번호", "email": "이메일",
             "card": "카드번호", "account": "계좌번호", "passport": "여권번호", "driver": "운전면허번호"}
    for f in warn[:50]:
        lines.append(f"  [경고] {f['location']} {names.get(f['rule'], f['rule'])}: {f['match']}  (…{f['context']}…)")
    for f in info[:10]:
        lines.append(f"  [허용] {f['location']} {names.get(f['rule'], f['rule'])}: {f['match']}")
    if warn:
        lines.append("  → 실제 개인정보라면 `privacy redact`로 가린 사본을 만들 수 있습니다.")
    return "\n".join(lines)
