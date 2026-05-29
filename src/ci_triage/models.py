from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Protocol, runtime_checkable


class FailureCategory(Enum):
    COMPILATION_ERROR = "compilation_error"
    TEST_FAILURE = "test_failure"
    FLAKY_TEST = "flaky_test"
    RESOURCE_EXHAUSTION = "resource_exhaustion"
    INFRA_FAILURE = "infra_failure"
    DEPENDENCY_FAILURE = "dependency_failure"
    TIMEOUT = "timeout"
    UNKNOWN = "unknown"


class CISource(Enum):
    JENKINS = "jenkins"
    GITHUB_ACTIONS = "github_actions"
    XCODEBUILD = "xcodebuild"
    GENERIC = "generic"


@dataclass(slots=True, frozen=True)
class LogEntry:
    line_number: int
    timestamp: str | None
    level: str | None
    message: str
    raw: str


@dataclass(slots=True, frozen=True)
class FailureSite:
    file: str | None
    line: int | None
    column: int | None
    test_name: str | None
    error_message: str
    context_lines: tuple[str, ...] = field(default_factory=tuple)


@dataclass(slots=True)
class ClassificationResult:
    category: FailureCategory
    confidence: float  # 0.0–1.0
    failure_sites: list[FailureSite]
    summary: str
    suggested_fix: str | None = None
    llm_used: bool = False


@dataclass(slots=True)
class TriageReport:
    build_id: str | None
    source: CISource
    timestamp: datetime.datetime
    classification: ClassificationResult
    flaky_test_scores: dict[str, float] = field(default_factory=dict)
    raw_log_lines: int = 0
    duration_ms: float = 0.0


@runtime_checkable
class LogParser(Protocol):
    source: CISource

    def parse(self, log_text: str) -> list[LogEntry]: ...

    def extract_failure_context(self, entries: list[LogEntry]) -> list[LogEntry]: ...


@runtime_checkable
class FailureClassifier(Protocol):
    def classify(self, entries: list[LogEntry]) -> ClassificationResult: ...


@runtime_checkable
class Reporter(Protocol):
    def report(self, triage: TriageReport) -> None: ...
