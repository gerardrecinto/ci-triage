from __future__ import annotations

import re
from ci_triage.models import CISource, LogEntry, FailureSite

# xcodebuild emits structured error lines:
#   /path/to/File.swift:42:17: error: use of unresolved identifier 'Foo'
_SWIFT_ERROR = re.compile(
    r"^(.+\.(?:swift|m|mm|c|cpp|h)):(\d+):(\d+):\s+(error|warning|note):\s+(.+)$"
)
# Test failure: "Test Case '-[SuiteTests testFoo]' failed (0.003 seconds)."
_TEST_FAILURE = re.compile(
    r"Test Case '(.+?)' (failed|passed)\s+\(([0-9.]+) seconds\)"
)
# xcresult summary lines: "** BUILD FAILED **", "** TEST FAILED **"
_BUILD_RESULT = re.compile(r"\*\* (BUILD|TEST) (SUCCEEDED|FAILED) \*\*")
# Linker errors
_LINKER_ERROR = re.compile(r"ld: (.+)")
# Code sign failures
_CODESIGN_ERROR = re.compile(r"CodeSign (.+) failed")
# Generic xcodebuild error marker
_XC_ERROR = re.compile(r"^error:\s+(.+)$", re.IGNORECASE)


class XcodebuildParser:
    source = CISource.XCODEBUILD

    def parse(self, log_text: str) -> list[LogEntry]:
        entries: list[LogEntry] = []
        for i, raw in enumerate(log_text.splitlines(), start=1):
            line = raw.rstrip()
            level: str | None = None
            message = line.strip()
            if _SWIFT_ERROR.match(line):
                m = _SWIFT_ERROR.match(line)
                level = m.group(4).upper() if m else None
            elif _BUILD_RESULT.search(line):
                level = "ERROR" if "FAILED" in line else "INFO"
            elif _XC_ERROR.match(line):
                level = "ERROR"
            elif _CODESIGN_ERROR.search(line):
                level = "ERROR"
            entries.append(LogEntry(
                line_number=i,
                timestamp=None,
                level=level,
                message=message,
                raw=raw,
            ))
        return entries

    def extract_failure_context(self, entries: list[LogEntry]) -> list[LogEntry]:
        result_idx: int | None = None
        for i, e in enumerate(entries):
            if _BUILD_RESULT.search(e.message) and "FAILED" in e.message:
                result_idx = i
                break
        if result_idx is None:
            return [e for e in entries if e.level == "ERROR"]
        return [e for e in entries[:result_idx] if e.level in ("ERROR", "WARNING")]

    def extract_failure_sites(self, entries: list[LogEntry]) -> list[FailureSite]:
        sites: list[FailureSite] = []
        seen: set[str] = set()
        for entry in entries:
            m = _SWIFT_ERROR.match(entry.raw)
            if m and m.group(4) == "error":
                key = f"{m.group(1)}:{m.group(2)}"
                if key not in seen:
                    seen.add(key)
                    sites.append(FailureSite(
                        file=m.group(1), line=int(m.group(2)), column=int(m.group(3)),
                        test_name=None, error_message=m.group(5),
                    ))
                continue
            m = _TEST_FAILURE.search(entry.message)
            if m and m.group(2) == "failed":
                sites.append(FailureSite(
                    file=None, line=None, column=None,
                    test_name=m.group(1),
                    error_message=f"test failed in {m.group(3)}s",
                ))
                continue
            m = _LINKER_ERROR.match(entry.message)
            if m:
                sites.append(FailureSite(
                    file=None, line=None, column=None,
                    test_name=None, error_message=f"linker: {m.group(1)}",
                ))
                continue
            m = _CODESIGN_ERROR.search(entry.message)
            if m:
                sites.append(FailureSite(
                    file=None, line=None, column=None,
                    test_name=None, error_message=f"codesign: {m.group(1)} failed",
                ))
        return sites

    @classmethod
    def from_file(cls, path: str) -> "XcodebuildParser":
        return cls()
