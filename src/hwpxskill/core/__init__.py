"""
hwpxskill.core 모듈.
"""
from .namespace import (
    NAMESPACES,
    register_all_namespaces,
    HP, HS, HH, HC, HA, HM, HPF, HHS, HP10
)
from .xml_utils import (
    safe_parse_xml,
    serialize_xml,
    clean_linesegarray,
    force_utf8_stdout
)
from .package import (
    unpack_hwpx,
    repack_hwpx,
    repack_with_replacements,
    write_with_lock_fallback,
    fix_namespaces
)

__all__ = [
    "NAMESPACES",
    "register_all_namespaces",
    "HP", "HS", "HH", "HC", "HA", "HM", "HPF", "HHS", "HP10",
    "safe_parse_xml",
    "serialize_xml",
    "clean_linesegarray",
    "force_utf8_stdout",
    "unpack_hwpx",
    "repack_hwpx",
    "repack_with_replacements",
    "write_with_lock_fallback",
    "fix_namespaces",
]
