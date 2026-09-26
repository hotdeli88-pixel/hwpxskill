"""
한컴오피스 HWPX 표준 규격 (KS X 6101) 네임스페이스 정의.
"""
from lxml import etree

NAMESPACES = {
    "hp": "http://www.hancom.co.kr/hwpml/2011/paragraph",
    "hs": "http://www.hancom.co.kr/hwpml/2011/section",
    "hh": "http://www.hancom.co.kr/hwpml/2011/head",
    "hc": "http://www.hancom.co.kr/hwpml/2011/core",
    "ha": "http://www.hancom.co.kr/hwpml/2011/app",
    "hp10": "http://www.hancom.co.kr/hwpml/2016/Hwp10",
    "hhs": "http://www.hancom.co.kr/hwpml/2011/history",
    "hm": "http://www.hancom.co.kr/hwpml/2011/master-page",
    "hpf": "http://www.hancom.co.kr/schema/2011/hwp",
    "opf": "http://www.idpf.org/2007/opf",
    "ocf": "urn:oasis:names:tc:opendocument:xmlns:container",
    "dc": "http://purl.org/dc/elements/1.1/",
    "config": "urn:oasis:names:tc:opendocument:xmlns:config:1.0",
    "xml": "http://www.w3.org/XML/1998/namespace",
}

# Alias for compatibility
NS = NAMESPACES


# Expanded name helpers
HP = f"{{{NAMESPACES['hp']}}}"
HS = f"{{{NAMESPACES['hs']}}}"
HH = f"{{{NAMESPACES['hh']}}}"
HC = f"{{{NAMESPACES['hc']}}}"
HA = f"{{{NAMESPACES['ha']}}}"
HM = f"{{{NAMESPACES['hm']}}}"
HPF = f"{{{NAMESPACES['hpf']}}}"
HHS = f"{{{NAMESPACES['hhs']}}}"
HP10 = f"{{{NAMESPACES['hp10']}}}"

def register_all_namespaces() -> None:
    """
    lxml 네임스페이스를 전역으로 사전 등록하여 ns0, ns1 등의 오염을 방지합니다.
    """
    for prefix, uri in NAMESPACES.items():
        if prefix != "xml":
            etree.register_namespace(prefix, uri)
