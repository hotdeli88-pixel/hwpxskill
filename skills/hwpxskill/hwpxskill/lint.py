"""공문서 표기법·개조식 문체 검사.

kordoc(MIT) hwpx/gongmun-lint.ts(22룰)·munche-lint.ts(12룰)를 옮겼다. 표기법 원전은
행정업무운영 편람과 jkf87/hwpx-skill gonmun_lint.py다. 검사는 조언용이며 채우기를 막지 않는다.
"""
from __future__ import annotations

import re
from typing import Callable, Dict, List, Optional, Tuple

LOANWORD_FIXES = [
    ("컨텐츠", "콘텐츠"), ("어플리케이션", "애플리케이션"), ("메세지", "메시지"), ("리더쉽", "리더십"),
    ("워크샵", "워크숍"), ("스케쥴", "스케줄"), ("악세사리", "액세서리"), ("네비게이션", "내비게이션"),
    ("타겟", "타깃"), ("화이팅", "파이팅"), ("비지니스", "비즈니스"), ("프리젠테이션", "프레젠테이션"),
    ("라이센스", "라이선스"), ("캐비넷", "캐비닛"), ("렌트카", "렌터카"), ("플랭카드", "플래카드"),
    ("플랜카드", "플래카드"), ("컨셉", "콘셉트"), ("심볼", "심벌"), ("카달로그", "카탈로그"),
    ("팜플렛", "팸플릿"), ("팜플릿", "팸플릿"), ("리모콘", "리모컨"), ("에어콘", "에어컨"), ("알콜", "알코올"),
    ("발란스", "밸런스"), ("매니아", "마니아"), ("코메디", "코미디"), ("판넬", "패널"), ("앵콜", "앙코르"),
    ("로보트", "로봇"), ("바베큐", "바비큐"), ("부페", "뷔페"), ("초코렛", "초콜릿"), ("카페트", "카펫"),
    ("케잌", "케이크"), ("도너츠", "도넛"), ("슈퍼마켙", "슈퍼마켓"), ("써비스", "서비스"), ("센타", "센터"),
]
DISCRIM_FIXES = [
    ("장애자", "장애인"), ("장애우", "장애인"), ("불구자", "장애인"), ("정신박약", "지적장애"), ("정상인", "비장애인"),
    ("편부모", "한부모"), ("결손가정", "한부모가정"), ("미망인", "고인의 배우자"), ("학부형", "학부모"),
    ("불우이웃", "어려운 이웃"), ("유모차", "유아차"), ("저출산", "저출생"), ("잡상인", "이동상인"),
    ("파출부", "가사도우미"), ("청소부", "환경미화원"), ("간호원", "간호사"), ("운전수", "운전기사"),
    ("노가다", "건설노동자"), ("조선족", "중국동포"), ("매매춘", "성매매"), ("사생아", "혼외자"),
    ("벙어리", "언어장애인"), ("절름발이", "지체장애인"), ("애꾸눈", "시각장애인"), ("귀머거리", "청각장애인"),
]


def _word_re(pairs) -> "re.Pattern[str]":
    return re.compile("|".join(re.escape(w) for w, _ in sorted(pairs, key=lambda x: -len(x[0]))))


_DIGITS = ["", "일", "이", "삼", "사", "오", "육", "칠", "팔", "구"]
_SMALL = ["", "십", "백", "천"]
_BIG = ["", "만", "억", "조", "경"]


def hangul_amount(n: str) -> str:
    digits = re.sub(r"\D", "", str(n)).lstrip("0")
    if not digits:
        return "영"
    groups = []
    for end in range(len(digits), 0, -4):
        groups.insert(0, digits[max(0, end - 4):end])
    out = ""
    for i, g in enumerate(groups):
        part = ""
        padded = g.zfill(4)
        for k in range(4):
            d = int(padded[k])
            if d:
                part += _DIGITS[d] + _SMALL[3 - k]
        if part:
            out += part + _BIG[len(groups) - 1 - i]
    return out


# (코드, 심각도, 정규식, 메시지, 제안, 표 줄 건너뜀, 추가 판정)
Rule = Tuple[str, str, "re.Pattern[str]", str, str, bool, Optional[Callable[[str, "re.Match[str]"], bool]]]


def _not_law_history(line: str, m: "re.Match[str]") -> bool:
    pre = line[:m.start()]
    return not (re.search(r"<(?:개정|신설|전문개정|전부개정|일부개정|제정)\s*$", pre)
                or re.search(r"삭제\s*<$", pre) or re.search(r"시행일\s*:\s*$", pre))


def _dueum_ok(line: str, m: "re.Match[str]") -> bool:
    pre, post = line[:m.start()], line[m.end():]
    if pre and re.match(r"[가-힣\d]", pre[-1]):
        return False
    if re.search(r"\d[ \t]{1,3}$", pre) or re.search(r"[(（>|][ \t]*$", pre) or re.search(r"[ \t][ \t]$", pre):
        return False
    if re.match(r"[ \t]*(?:</t[dh]>|\|)", post):
        return False
    return True


RULES: List[Rule] = [
    ("DATE_NO_SPACE", "error", re.compile(r"\b\d{4}\.\d{1,2}\.\d{1,2}\.?"),
     "날짜 온점 뒤에 한 칸씩 띄워야 함", "예) 2025. 1. 6.", False, _not_law_history),
    ("DATE_ZERO_PAD", "error", re.compile(r"\b\d{4}\.\s*0\d\.|\b\d{4}\.\s*\d{1,2}\.\s*0\d"),
     "월·일 앞의 '0'은 표기하지 않음", "예) 2025. 1. 6. (2025. 01. 06. ✕)", False, None),
    ("DATE_2DIGIT_YR", "error", re.compile(r"(?<!\d)['’]\d{2}\.\s*\d"),
     "연도는 네 자리로 표기('24 ✕)", "예) 2025. 1. 6.", False, None),
    ("DATE_NO_END_DOT", "warning", re.compile(r"\b\d{4}\.\s\d{1,2}\.\s\d{1,2}(?!\s*[.\d(])"),
     "날짜의 '일' 다음에 마침표(.)를 찍어야 함", "예) 2025. 1. 6.", False, None),
    ("DATE_HYPHEN", "warning", re.compile(r"(?<![/=&?#%.\w-])(?:19|20)\d{2}-\d{1,2}-\d{1,2}(?![/\w-])"),
     "날짜는 하이픈(-) 대신 온점으로 구분하고 온점 뒤 한 칸 띄움", "예) 2026. 7. 18.", True, None),
    ("TIME_AMPM", "error", re.compile(r"(오전|오후|아침|밤|낮)\s*\d{1,2}\s*시"),
     "24시각제 숫자로 표기(오전/오후 사용 안 함)", "예) 09:00, 15:30", False, None),
    ("TIME_24H", "warning", re.compile(r"(?<!\d)24\s*시(?!각)"),
     "'24시'보다 익일 00:00 또는 '18:00까지' 권장", "예) 18:00", False, None),
    ("TIME_COLON_SP", "error", re.compile(r"\b\d{1,2}\s+:\s*\d{2}\b|\b\d{1,2}:\s+\d{2}\b"),
     "시와 분 사이 쌍점은 양쪽을 붙여 씀", "예) 13:20", False, None),
    ("MONEY_CHEONWON", "error", re.compile(r"\d+\s*천\s*원"),
     "금액은 '천원'으로 줄이지 않고 아라비아 숫자로", "예) 345,000원", False, None),
    ("MONEY_GEUM_SP", "warning", re.compile(r"금\s+\d"),
     "'금'과 숫자 사이는 붙여 쓰는 것이 원칙", "예) 금113,560원", False, None),
    ("BUNIM_COLON", "error", re.compile(r"붙\s*임\s*:"),
     "'붙임' 다음에 쌍점(:)을 붙이지 않음(2타 띄움)", "예) 붙임  계획서 1부.", False, None),
    ("KKAJI_DUP", "error", re.compile(r"[∼~～][^\n]{0,20}?까지"),
     "물결표(∼)와 '까지'를 함께 쓰지 않음", "예) 2. 20.∼2. 24.", False, None),
    ("FOREIGN_FIRST", "warning", re.compile(r"\b[A-Z]{2,5}\s*\([가-힣]"),
     "한글을 먼저 쓰고 괄호 안에 외국어를 병기", "예) 업무 협약(MOU)", False, None),
    ("COLON_SPACE", "warning", re.compile(r"\S\s+:(?!//)|\S:(?!//)[^\s\d<*_]"),
     "쌍점은 앞말에 붙이고 뒤는 한 칸 띄움", "예) 원장: 김갑동", True, None),
    ("MONEY_NO_HANGUL", "warning", re.compile(r"금\d[\d,]*원(?![\s]*[(（])"),
     "금액은 숫자 다음 괄호 안에 한글 병기", "예) 금113,560원(금일십일만삼천오백육십원)", False, None),
    ("TILDE_SPACE", "warning", re.compile(r"(?<=[\d.)일월년시분’'])[ \t]+[∼~～]|[∼~～][ \t]+(?=[\d'’])"),
     "물결표(∼) 앞뒤는 붙여 씀", "예) 2. 20.∼2. 24., 09:00∼18:00", False, None),
    ("DUEUM_ERROR", "warning", re.compile(r"년(?:도별|도|간|말|초|차|세|내)(?![가-힣])"),
     "어두의 '년'은 두음법칙에 따라 '연'으로 적음", "예) 연도, 연간, 연말, 연초", False, _dueum_ok),
    ("LOANWORD_ERROR", "warning", _word_re(LOANWORD_FIXES),
     "외래어 표기법에 맞지 않는 표기", "예) 콘텐츠·애플리케이션·메시지·워크숍·스케줄·콘셉트", False, None),
    ("DISCRIMINATORY_TERM", "warning", _word_re(DISCRIM_FIXES),
     "차별·비하 표현은 순화어로", "예) 장애자→장애인, 편부모→한부모, 학부형→학부모", False, None),
    ("AI_EM_DASH", "warning", re.compile(r"[—–―]"),
     "줄표(— – ―)는 공문서 표기 관행에 맞지 않음(생성형 AI 문체 흔적)", "쉼표·괄호·가운뎃점(·)으로 풀어쓰기", False, None),
    ("AI_BOLD_OVERUSE", "warning", re.compile(r"(?:\*\*[^*\n]+\*\*[^*\n]*){3}"),
     "한 줄에 강조(**) 3회 이상 — 강조 남발은 생성형 AI 문체 흔적", "리드어·핵심 수치 한 곳만 강조", False, None),
]


def _suggest(code: str, match: str, default: str) -> str:
    m = match.strip()
    if code == "MONEY_NO_HANGUL":
        return f"{m} → {m}(금{hangul_amount(m)}원)"
    if code == "DATE_HYPHEN":
        d = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})$", m)
        if d:
            return f"{m} → {d.group(1)}. {int(d.group(2))}. {int(d.group(3))}."
    table = LOANWORD_FIXES if code == "LOANWORD_ERROR" else DISCRIM_FIXES if code == "DISCRIMINATORY_TERM" else None
    if table:
        for w, fix in table:
            if w == m:
                return f"{w} → {fix}"
    return default


def lint_lines(lines: List[Tuple[str, str, bool]], document: bool = False) -> List[Dict]:
    """lines = [(위치, 글, 표 칸 여부)]"""
    out: List[Dict] = []
    for loc, line, in_table in lines:
        for code, sev, pat, msg, sug, skip_table, extra in RULES:
            if skip_table and in_table:
                continue
            for m in pat.finditer(line):
                if extra is not None and not extra(line, m):
                    continue
                out.append({"location": loc, "rule": code, "severity": sev, "match": m.group(0).strip(),
                            "message": msg, "suggest": _suggest(code, m.group(0), sug)})
    if document:
        full = "\n".join(t for _, t, _ in lines)
        if re.search(r"^\s*붙\s*임(?![가-힣])", full, re.M) and not re.search(r"끝\.\s*$", full, re.M):
            out.append({"location": lines[-1][0] if lines else "", "rule": "END_MARK_MISSING",
                        "severity": "warning", "match": "붙임", "message": "붙임 표시 뒤에 '끝.' 표시가 없음",
                        "suggest": "예) 붙임  계획서 1부.  끝."})
    return out


# ── 개조식 문체 ───────────────────────────────────────────────────────────
_DA = re.compile(r"[가-힣]다\.?$")
_DEONTIC = re.compile(r"[가-힣]야\s*(?:한다|함|합니다|하겠음)\.?$|필요가\s*있(?:다|음|습니다)\.?$|할 것\.?$")
_GEOSIDA = re.compile(r"것(?:이다|임)\.?$")
_LEAD_END = re.compile(r"(?:하고자|하려|고자)\s*함\.?$")
_NOT_A_BUT = re.compile(r"(?:아니라|아닌|아니고|아니며)\s*,?\s*([가-힣]{1,12})")
_ABSTRACT = ["사람", "마음", "본질", "전환", "태도", "문화", "철학", "가치", "정신", "관계", "신뢰", "과정", "질문",
             "이야기", "경험", "시간", "공간", "연결", "변화", "미래", "시작", "용기", "의지", "방법", "자세", "의식", "역량"]
_COUPLET = re.compile(r"[은는이가]\s*[^,]{2,15},\s*[^,]{2,15}[은는이가]\s*[^,]{2,15}$")
_DATE_KO = re.compile(r"\d{4}년\s*\d{1,2}월")


def _classify(raw: str) -> Optional[Tuple[str, str]]:
    indent = len(raw) - len(raw.lstrip())
    t = raw.strip()
    if not t or t.startswith(("#", "|", "![")) or re.fullmatch(r"[-=*_]{3,}", t):
        return None
    if t.startswith(">"):
        return "lead", t[1:].strip()
    if re.match(r"^(?:⇒|=>|➡|→)", t):
        return "concl", re.sub(r"^(?:⇒|=>|➡|→)\s*", "", t)
    if re.match(r"^(?:※|\*\s)", t):
        return "note", re.sub(r"^(?:※|\*)\s*", "", t)
    if t.startswith("□"):
        return "dae", t[1:].strip()
    if re.match(r"^(?:○|❍|ㅇ|◦)", t):
        return "item", t[1:].strip()
    li = re.match(r"^(?:[-•ㆍ·]|\d+[.)])\s+(.*)$", t)
    if li:
        return ("sub" if indent >= 2 else "item"), li.group(1).strip()
    return "para", t


def lint_munche(lines: List[Tuple[str, str, bool]]) -> List[Dict]:
    out: List[Dict] = []

    def add(loc, sev, rule, match, msg, sug=""):
        out.append({"location": loc, "rule": rule, "severity": sev, "match": match[:60], "message": msg,
                    "suggest": sug})

    for loc, raw, in_table in lines:
        c = _classify(raw)
        if c is None:
            continue
        kind, body = c
        b = re.sub(r"(\*\*|__|~~|`)", "", body).strip()
        if not b:
            continue
        q = re.sub(r"[“\"'‘][^”\"'’]{0,80}[”\"'’]", "", b)
        q = re.sub(r"\([^)]{0,80}\)", "", q)
        if kind == "lead":
            if len(b) >= 20 and not _LEAD_END.search(b):
                add(loc, "warning", "LEAD_ENDING", b, "리드문은 '~하고자 함.' 한 문장", "[수단]하고 [목적]하고자 함.")
            if len(b) > 140 or b.count(".") > 1:
                add(loc, "warning", "LEAD_LONG", b, f"리드문 {len(b)}자 — 한 문장 40~120자 권장")
            continue
        if kind in ("item", "sub", "concl", "para"):
            if _DA.search(q):
                add(loc, "error", "DA_ENDING", b, "'~다' 서술형 종결 — 개조식은 명사형으로", "명사·명사구 또는 '~함/있음'으로")
            if _GEOSIDA.search(q):
                add(loc, "warning", "GEOSIDA", b, "'~것이다/것임' 종결", "명사 종결로")
        if _DEONTIC.search(q):
            add(loc, "error", "DEONTIC", b, "'~해야 한다' 당위 종결 — 판단은 명사로 끝맺음", "예) ⇒ 지역맞춤형 보급 필요")
        for m in _NOT_A_BUT.finditer(q):
            tail = m.group(1)
            if any(w in tail for w in _ABSTRACT):
                add(loc, "error", "RHETORIC_CONTRAST", m.group(0), f"'아니라 {tail}' — 추상어 대조는 수사")
            else:
                add(loc, "warning", "CONTRAST_CHECK", m.group(0), f"'아니라 {tail}' — 구체 선택지인지 확인")
        if kind != "note" and re.search(r"[?!？！]", q):
            add(loc, "error", "QUESTION_EXCLAIM", b, "물음표·느낌표 — 개조식 본문에 쓰지 않음")
        if kind in ("item", "para", "dae") and _COUPLET.search(q):
            add(loc, "warning", "COUPLET", b, "대구(對句)로 보임 — 슬로건 문장 대신 목표 수치·명사로")
        if kind == "item" and len(b) > 70:
            add(loc, "warning", "ITEM_LONG", b, f"항목 {len(b)}자 — 2줄 이내 권장", "근거·예시는 세부(-)로 내림")
        if kind == "concl" and len(b) > 60:
            add(loc, "warning", "CONCL_LONG", b, f"결론 {len(b)}자 — 판단 하나만 남김")
        if _DATE_KO.search(b):
            add(loc, "warning", "DATE_KOREAN", b, "연·월을 글자로 표기", "예) 2026. 8. 22.")
    return out


def lint_text(text: str, munche: bool = False, document: bool = False) -> List[Dict]:
    lines = []
    fence = False
    for i, raw in enumerate(text.replace("\r\n", "\n").split("\n")):
        if re.match(r"^\s*(```|~~~)", raw):
            fence = not fence
            continue
        if fence:
            continue
        in_table = raw.lstrip().startswith("|") or bool(re.search(r"<t[dhr][\s>]", raw, re.I))
        lines.append((f"L{i + 1}", raw, in_table))
    out = lint_lines(lines, document=document)
    if munche:
        out += lint_munche(lines)
    return out


def document_lines(doc) -> List[Tuple[str, str, bool]]:
    from .core.model import Section
    from .core.text import ParaText
    lines = []
    for si in range(len(doc.section_paths)):
        sec = Section(doc, si)
        for p in sec.iter_paragraphs():
            t = ParaText(sec.src, p).text
            if not t.strip():
                continue
            lines.append((sec.paragraph_address(p), t.replace("\t", " "), p.ancestor("tc") is not None))
    return lines


def lint_document(doc, munche: bool = False) -> List[Dict]:
    lines = document_lines(doc)
    out = lint_lines(lines, document=True)
    if munche:
        out += lint_munche(lines)
    return out


def format_findings(findings: List[Dict]) -> str:
    if not findings:
        return "표기법 검사: 문제 없음"
    errs = sum(1 for f in findings if f["severity"] == "error")
    lines = [f"표기법 검사: 오류 {errs}건, 경고 {len(findings) - errs}건"]
    for f in findings[:80]:
        tag = "오류" if f["severity"] == "error" else "경고"
        lines.append(f"  [{tag}] {f['location']} {f['rule']} “{f['match']}” — {f['message']} ({f['suggest']})")
    if len(findings) > 80:
        lines.append(f"  … {len(findings) - 80}건 더")
    return "\n".join(lines)
