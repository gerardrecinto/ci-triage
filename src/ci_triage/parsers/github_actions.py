from __future__ import annotations

import re
from ci_triage.models import CISource, LogEntry, FailureSite

# GHA annotated log line: ##[group]..., ##[error]..., ##[warning]...
_GHA_ANNOTATION = re.compile(r"^##\[(\w+)\](.*)$")
# GHA timestamp prefix: 2024-05-28T03:14:15.0000000Z  (RFC 3339)
_GHA_TS = re.compile(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+Z)\s+")

_PYTEST_FAIL = re.compile(r"^FAILED\s+(.+?)\s*(?:- (.+))?$")
_PYTEST_ERR = re.compile(r"^ERROR\s+(.+)")
_NPM_ERR = re.compile(r"^npm ERR!\s+(.+)")
_GHA_ERROR_FILE = re.compile(
    r"^::error file=(.+?),line=(\d+)(?:,col=(\d+))?::(.+)$"
)
_STEP_FAILED = re.compile(r"^Process completed with exit code (\d+)")


class GitHubActionsParser:
    source = CISource.GITHUB_ACTIONS

    def parse(self, log_text: str) -> list[LogEntry]:
        entries: list[LogEntry] = []
        for i, raw in enumerate(log_text.splitlines(), start=1):
            line = raw.rstrip()
            ts_match = _GHA_TS.match(line)
            timestamp = ts_match.group(1) if ts_match else None
            body = line[ts_match.end():] if ts_match else line
            ann = _GHA_ANNOTATION.match(body)
            if ann:
                level = ann.group(1).upper()
                message = ann.group(2).strip()
            else:
                level = None
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
        error_indices = [
            i for i, e in enumerate(entries)
            if e.level in ("ERROR", "ENDGROUP") or "exit code" in e.message.lower()
        ]
        if not error_indices:
            return entries[-60:]
        first = error_indices[0]
        start = max(0, first - 5)
        return entries[start:]

    def extract_failure_sites(self, entries: list[LogEntry]) -> list[FailureSite]:
        sites: list[FailureSite] = []
        for entry in entries:
            m = _GHA_ERROR_FILE.match(entry.message)
            if m:
                sites.append(FailureSite(
                    file=m.group(1), line=int(m.group(2)),
                    column=int(m.group(3)) if m.group(3) else None,
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
            m = _NPM_ERR.match(entry.message)
            if m:
                sites.append(FailureSite(
                    file=None, line=None, column=None,
                    test_name=None, error_message=m.group(1),
                ))
                continue
            m = _STEP_FAILED.match(entry.message)
            if m:
                sites.append(FailureSite(
                    file=None, line=None, column=None,
                    test_name=None,
                    error_message=f"step exited with code {m.group(1)}",
                ))
        return sites

    @classmethod
    def from_file(cls, path: str) -> "GitHubActionsParser":
        return cls()
