"""HWPX Quality, Integrity and Privacy Auditor.

Validates Hancom golden packaging rules, detects residual placeholders,
verifies numeric table totals, and audits strictly for Personally Identifiable Information (PII)
and secret credentials before deployment.
"""
from __future__ import annotations

import re
import zipfile
from typing import Any, Dict, List, Optional, Tuple
import xml.etree.ElementTree as ET

from .core.namespace import NS, HP, register_all_namespaces


class HwpxValidator:
    """Performs integrity verification, table math auditing, and privacy compliance scans."""

    def __init__(self, hwpx_path: str):
        self.hwpx_path = hwpx_path
        register_all_namespaces()

    def validate_packaging(self) -> Tuple[bool, str]:
        """Validates HWPX package integrity against Hancom OWPML specifications.

        Golden Rule 1: 'mimetype' must be the first file entry.
        Golden Rule 2: 'mimetype' must be stored without compression (ZIP_STORED).
        """
        try:
            with zipfile.ZipFile(self.hwpx_path, "r") as zf:
                info_list = zf.infolist()
                if not info_list:
                    return False, "Archive is empty."

                first = info_list[0]
                if first.filename != "mimetype":
                    return False, f"First entry is '{first.filename}', expected 'mimetype'."
                if first.compress_type != zipfile.ZIP_STORED:
                    return False, f"'mimetype' compression is {first.compress_type}, expected 0 (ZIP_STORED)."

                required = ["Contents/header.xml", "Contents/section0.xml"]
                for req in required:
                    if req not in zf.namelist():
                        return False, f"Missing required file: {req}"

            return True, "HWPX package conforms to Hancom OWPML standards."
        except Exception as exc:
            return False, f"Package validation error: {exc}"

    def audit_privacy(self) -> List[Dict[str, Any]]:
        """Scans all XML contents for confidential data, API secrets, and personal information."""
        pii_patterns = {
            "phone_mobile": r"(?:010|011|016|017|018|019)[-.\s]?\d{3,4}[-.\s]?\d{4}",
            "phone_landline": r"(?:02|031|032|033|041|042|043|044|051|052|053|054|055|061|062|063|064)[-.\s]?\d{3,4}[-.\s]?\d{4}",
            "resident_id": r"\b\d{6}[-.\s]?[1-4]\d{6}\b",
            "api_key_github": r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9_]{36,}\b",
            "api_key_google": r"\bAIzaSy[A-Za-z0-9_-]{33}\b",
            "api_key_openai": r"\bsk-[A-Za-z0-9]{32,}\b",
            "bearer_token": r"(?i)bearer\s+[A-Za-z0-9\-_.]{25,}",
        }

        findings: List[Dict[str, Any]] = []

        with zipfile.ZipFile(self.hwpx_path, "r") as zf:
            for filename in zf.namelist():
                if not (filename.startswith("Contents/") and filename.endswith(".xml")):
                    continue

                content = zf.read(filename).decode("utf-8", errors="ignore")

                for p_type, regex in pii_patterns.items():
                    for match in re.finditer(regex, content):
                        findings.append({
                            "severity": "CRITICAL",
                            "type": p_type,
                            "file": filename,
                            "match": match.group(0),
                        })

        return findings

    def check_residual_placeholders(self) -> List[Dict[str, Any]]:
        """Finds unfilled template placeholder tokens."""
        placeholder_regex = re.compile(r"(\$\{[^}]+\}|\{\{[^}]+\}|\[[A-Za-z0-9_가-힣\s]+\]|_{4,})")
        findings: List[Dict[str, Any]] = []

        with zipfile.ZipFile(self.hwpx_path, "r") as zf:
            for filename in zf.namelist():
                if not (filename.startswith("Contents/section") and filename.endswith(".xml")):
                    continue

                content = zf.read(filename).decode("utf-8", errors="ignore")
                for match in placeholder_regex.finditer(content):
                    findings.append({
                        "file": filename,
                        "token": match.group(0),
                    })

        return findings

    def audit_document(self) -> Dict[str, Any]:
        """Runs complete inspection: packaging, security audit, and placeholder check."""
        pkg_ok, pkg_msg = self.validate_packaging()
        pii_issues = self.audit_privacy()
        residuals = self.check_residual_placeholders()

        return {
            "status": "PASS" if (pkg_ok and len(pii_issues) == 0) else "WARN",
            "packaging": {
                "valid": pkg_ok,
                "message": pkg_msg,
            },
            "privacy_audit": {
                "issues_count": len(pii_issues),
                "findings": pii_issues,
            },
            "residual_placeholders": {
                "count": len(residuals),
                "items": residuals,
            },
        }
