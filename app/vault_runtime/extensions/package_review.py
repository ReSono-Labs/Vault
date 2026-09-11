"""Non-executing risk review for quarantined Plugin packages."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re


_EXECUTABLE_SUFFIXES = {".bat", ".cmd", ".com", ".exe", ".js", ".mjs", ".ps1", ".py", ".sh"}
_SECRET_PATTERNS = (
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
)
_INSTRUCTION_PATTERNS = (
    ("ignore previous", "attempts to override prior instructions"),
    ("reveal your system prompt", "requests hidden system instructions"),
    ("disable safety", "requests safety controls be disabled"),
    ("send credentials", "requests credential disclosure"),
)
_TEXT_LIMIT = 1_000_000


@dataclass(frozen=True, slots=True)
class PackageReviewFinding:
    severity: str
    code: str
    path: str
    message: str


@dataclass(frozen=True, slots=True)
class PackageReview:
    risk: str
    findings: tuple[PackageReviewFinding, ...]

    @property
    def diagnostics(self) -> tuple[str, ...]:
        return tuple(
            f"review:{item.severity}:{item.code}:{item.path}: {item.message}"
            for item in self.findings
        )


def _review_relative_path(relative: str) -> bool:
    """Skip migration payloads — they are copied to package data, not installed as code."""
    return not relative.startswith("migration/")


def review_plugin_package(root: Path) -> PackageReview:
    """Inspect package content without importing, executing, or contacting a model."""
    findings: list[PackageReviewFinding] = []
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative = path.relative_to(root).as_posix()
        if not _review_relative_path(relative):
            continue
        suffix = path.suffix.casefold()
        if suffix in _EXECUTABLE_SUFFIXES:
            findings.append(PackageReviewFinding(
                "medium", "executable-content", relative,
                "contains code or a script; Vault will not execute it automatically",
            ))
        content = path.read_bytes()
        if len(content) > _TEXT_LIMIT or b"\x00" in content:
            continue
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError:
            continue
        for pattern in _SECRET_PATTERNS:
            if pattern.search(text):
                findings.append(PackageReviewFinding(
                    "high", "embedded-secret", relative,
                    "appears to contain a credential or private key",
                ))
                break
        folded = text.casefold()
        for phrase, message in _INSTRUCTION_PATTERNS:
            if phrase in folded:
                findings.append(PackageReviewFinding(
                    "high", "suspicious-instruction", relative, message,
                ))
    severities = {item.severity for item in findings}
    risk = "high" if "high" in severities else "medium" if "medium" in severities else "low"
    return PackageReview(risk, tuple(findings))
