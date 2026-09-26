"""
XML 파싱 및 시리얼라이제이션 헬퍼.
"""
import sys
from typing import Union
from lxml import etree
from .namespace import HP

def safe_parse_xml(xml_content: bytes) -> etree._ElementTree:
    """
    XML 컨텐츠를 파싱합니다.
    
    Args:
        xml_content: 파싱할 XML 바이트 배열
        
    Returns:
        etree._ElementTree 객체
    """
    parser = etree.XMLParser(remove_blank_text=False)
    return etree.fromstring(xml_content, parser=parser).getroottree()

def serialize_xml(tree: Union[etree._ElementTree, etree._Element]) -> bytes:
    """
    ElementTree 객체를 XML 바이트 배열로 직렬화합니다.
    
    Args:
        tree: lxml ElementTree 또는 Element
        
    Returns:
        XML 바이트 배열
    """
    return etree.tostring(
        tree,
        encoding="UTF-8",
        xml_declaration=True,
        standalone=True,
        pretty_print=False,
    )

def clean_linesegarray(tree: etree._ElementTree) -> None:
    """
    HWPX 문서의 렌더링 캐시(linesegarray)를 무효화(제거)합니다.
    
    Args:
        tree: 변경할 XML 트리
    """
    for elem in tree.findall(f".//{HP}linesegarray"):
        parent = elem.getparent()
        if parent is not None:
            parent.remove(elem)

def force_utf8_stdout() -> None:
    """
    Windows 환경 등에서 표준 출력을 UTF-8로 강제합니다.
    """
    if sys.stdout.encoding.lower() != 'utf-8':
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8')
