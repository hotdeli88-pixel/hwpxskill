"""
HWPX 패키지(ZIP) 압축 해제 및 재압축, 파일 저장 락 회피 기능.
"""
import os
import zipfile
from pathlib import Path
from typing import Dict, Union

def unpack_hwpx(hwpx_path: Union[str, Path]) -> Dict[str, bytes]:
    """
    HWPX 파일을 읽어 내부 파일 경로와 바이너리 데이터를 딕셔너리로 반환합니다.
    
    Args:
        hwpx_path: HWPX 파일 경로
        
    Returns:
        파일 경로를 키로, 파일 내용을 값으로 가지는 딕셔너리
    """
    entries = {}
    with zipfile.ZipFile(hwpx_path, 'r') as zf:
        for name in zf.namelist():
            entries[name] = zf.read(name)
    return entries

def repack_hwpx(entries: Dict[str, bytes], output_path: Union[str, Path]) -> None:
    """
    딕셔너리 안의 데이터를 HWPX(ZIP) 형식으로 압축합니다.
    골든 룰: mimetype은 반드시 첫 번째 엔트리여야 하며 ZIP_STORED(무압축)로 저장되어야 합니다.
    나머지는 ZIP_DEFLATED로 압축합니다.
    
    Args:
        entries: 압축할 파일 경로와 데이터
        output_path: 저장할 HWPX 파일 경로
    """
    with zipfile.ZipFile(output_path, 'w') as zf:
        if 'mimetype' in entries:
            zf.writestr('mimetype', entries['mimetype'], compress_type=zipfile.ZIP_STORED)
        
        for name, data in entries.items():
            if name == 'mimetype':
                continue
            zf.writestr(name, data, compress_type=zipfile.ZIP_DEFLATED)

def repack_with_replacements(src_hwpx: Union[str, Path], dst_hwpx: Union[str, Path], replacements_dict: Dict[str, bytes]) -> None:
    """
    원본 HWPX 파일의 내용을 기반으로 일부 파일을 교체하여 새 HWPX 파일을 생성합니다.
    
    Args:
        src_hwpx: 원본 HWPX 파일 경로
        dst_hwpx: 대상 HWPX 파일 경로
        replacements_dict: 교체할 파일 경로와 새 데이터
    """
    entries = unpack_hwpx(src_hwpx)
    entries.update(replacements_dict)
    repack_hwpx(entries, dst_hwpx)

def write_with_lock_fallback(path: Union[str, Path], data: bytes, max_fallback: int = 99) -> Path:
    """
    파일을 저장할 때 한컴오피스 등에서 열려 있어 잠겨있는 경우,
    _v1, _v2 등을 붙여서 저장합니다.
    
    Args:
        path: 저장할 파일 경로
        data: 저장할 바이너리 데이터
        max_fallback: 최대 폴백 시도 횟수
        
    Returns:
        실제 저장된 파일 경로
    """
    path_obj = Path(path)
    base_dir = path_obj.parent
    stem = path_obj.stem
    ext = path_obj.suffix
    
    for i in range(max_fallback + 1):
        if i == 0:
            current_path = path_obj
        else:
            current_path = base_dir / f"{stem}_v{i}{ext}"
            
        try:
            with open(current_path, 'wb') as f:
                f.write(data)
            return current_path
        except PermissionError:
            continue
            
    raise PermissionError(f"Could not save file, all fallbacks exhausted up to _v{max_fallback}")

def fix_namespaces(xml_content: Union[bytes, str, Path]) -> bytes:
    """
    잘못 생성된 ns0, ns1 네임스페이스 등을 hp, hs 등으로 정규화합니다.
    
    Args:
        xml_content: XML 바이트 배열, 문자열, 혹은 파일 경로
        
    Returns:
        정규화된 XML 바이트 배열
    """
    if isinstance(xml_content, Path) or (isinstance(xml_content, str) and os.path.exists(xml_content)):
        with open(xml_content, 'rb') as f:
            content = f.read()
    elif isinstance(xml_content, str):
        content = xml_content.encode('utf-8')
    else:
        content = xml_content
        
    from lxml import etree
    from .namespace import register_all_namespaces, NAMESPACES
    
    register_all_namespaces()
    
    parser = etree.XMLParser(remove_blank_text=False)
    tree = etree.fromstring(content, parser=parser)
    
    etree.cleanup_namespaces(tree, top_nsmap=NAMESPACES, keep_ns_prefixes=list(NAMESPACES.keys()))
    
    return etree.tostring(
        tree,
        encoding="UTF-8",
        xml_declaration=True,
        standalone=True
    )


class HwpxPackager:
    """HWPX ZIP packaging and unpackaging helper class."""
    unpack = staticmethod(unpack_hwpx)
    repack = staticmethod(repack_hwpx)
    repack_with_replacements = staticmethod(repack_with_replacements)
    write_with_lock_fallback = staticmethod(write_with_lock_fallback)
    fix_namespaces = staticmethod(fix_namespaces)

