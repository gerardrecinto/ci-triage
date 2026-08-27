from __future__ import annotations

import re
from ci_triage.models import CISource, LogEntry, FailureSite

# Timestamp formats Jenkins writes to console output
_TS_RE = re.compile(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z?)\s+")
_LEVEL_RE = re.compile(r"\[(INFO|WARN|WARNING|ERROR|DEBUG|FATAL)\]", re.IGNORECASE)

# Build-failure markers Jenkins emits
_BUILD_FAILURE = re.compile(r"BUILD (FAILURE|FAILED|ERROR)", re.IGNORECASE)
_PERMISSION_RE = re.compile(
    r"(permission denied|access denied|operation not permitted|ScriptSecurityException|RejectedAccessException|scripts not permitted|403 Forbidden|401 Unauthorized|EACCES|EPERM)",
    re.IGNORECASE,
)
_EXCEPTION_RE = re.compile(r"(Exception|Error):\s+(.+)$")
_MAVEN_COMPILE = re.compile(r"^\[ERROR\]\s+(.+\.java):(\d+):\s+error:\s+(.+)")
_GRADLE_COMPILE = re.compile(r"^e:\s+(.+\.kt):(\d+):(\d+):\s+(.+)")
_PYTEST_FAIL = re.compile(r"^FAILED\s+(.+?)\s*(?:- (.+))?$")
_PYTEST_ERROR = re.compile(r"^ERROR\s+(.+)")


class JenkinsParser:
    source = CISource.JENKINS

    def parse(self, log_text: str) -> list[LogEntry]:
        entries: list[LogEntry] = []
        for i, raw in enumerate(log_text.splitlines(), start=1):
            line = raw.rstrip()
            ts_match = _TS_RE.match(line)
            timestamp = ts_match.group(1) if ts_match else None
            body = line[ts_match.end():] if ts_match else line
            level_match = _LEVEL_RE.search(body)
            level = level_match.group(1).upper() if level_match else None
            message = body.strip()
            entries.append(LogEntry(
                line_number=i,
                timestamp=timestamp,
                level=level,
                message=message,
                raw=raw,
            ))
        return entries

    def extract_failure_context(self, entries: list[LogEntry]) -> list[LogEntry]:
        """Return entries around the failure signal: 10 lines before, all after."""
        failure_idx: int | None = None
        for i, entry in enumerate(entries):
            if _BUILD_FAILURE.search(entry.message):
                failure_idx = i
                break
        if failure_idx is None:
            for i, entry in enumerate(entries):
                if _PERMISSION_RE.search(entry.message):
                    failure_idx = i
                    break
        if failure_idx is None:
            # No explicit BUILD FAILURE line: return last 50 entries
            return entries[-50:]
        start = max(0, failure_idx - 10)
        return entries[start:]

    def extract_failure_sites(self, entries: list[LogEntry]) -> list[FailureSite]:
        sites: list[FailureSite] = []
        for entry in entries:
            m = _MAVEN_COMPILE.match(entry.message)
            if m:
                sites.append(FailureSite(
                    file=m.group(1), line=int(m.group(2)), column=None,
                    test_name=None, error_message=m.group(3),
                ))
                continue
            m = _GRADLE_COMPILE.match(entry.message)
            if m:
                sites.append(FailureSite(
                    file=m.group(1), line=int(m.group(2)), column=int(m.group(3)),
                    test_name=None, error_message=m.group(4),
                ))
                continue
            m = _PYTEST_FAIL.match(entry.message)
            if m:
                sites.append(FailureSite(
                    file=None, line=None, column=None,
                    test_name=m.group(1),
                    error_message=m.group(2) or "assertion failed",
                ))
                continue
            m = _PERMISSION_RE.search(entry.message)
            if m:
                sites.append(FailureSite(
                    file=None, line=entry.line_number, column=None,
                    test_name=None, error_message=entry.message,
                ))
                continue
            m = _EXCEPTION_RE.search(entry.message)
            if m and (entry.level in ("ERROR", "FATAL") or "Security" in m.group(1) or "Access" in m.group(1) or "Permission" in m.group(1)):
                sites.append(FailureSite(
                    file=None, line=entry.line_number, column=None,
                    test_name=None, error_message=f"{m.group(1)}: {m.group(2)}",
                ))
        return sites

    @classmethod
    def from_file(cls, path: str) -> "JenkinsParser":
        return cls()

