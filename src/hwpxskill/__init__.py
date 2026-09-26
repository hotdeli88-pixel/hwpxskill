"""
hwpxskill: HWPX Document Engine & Multi-Agent Swarm Workflows.

A unified framework for analyzing, styling, editing, and packaging Hancom HWPX documents,
powered by a 5-agent collaborative workflow and automated privacy auditing.
"""

from .analyzer import HwpxAnalyzer
from .styler import HwpxStyler
from .editor import HwpxEditor
from .core.package import (
    HwpxPackager,
    unpack_hwpx,
    repack_hwpx,
    repack_with_replacements,
    write_with_lock_fallback,
    fix_namespaces,
)
from .validator import HwpxValidator
from .workflows.orchestrator import HwpxTeamWorkflow, run_pipeline

__version__ = "1.0.0"

__all__ = [
    "HwpxAnalyzer",
    "HwpxStyler",
    "HwpxEditor",
    "HwpxPackager",
    "HwpxValidator",
    "HwpxTeamWorkflow",
    "run_pipeline",
    "unpack_hwpx",
    "repack_hwpx",
    "repack_with_replacements",
    "write_with_lock_fallback",
    "fix_namespaces",
]
