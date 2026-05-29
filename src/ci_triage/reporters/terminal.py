from __future__ import annotations

import sys
from ci_triage.models import FailureCategory, TriageReport

_ANSI = {
    "reset": "\033[0m",
    "bold": "\033[1m",
    "red": "\033[91m",
    "yellow": "\033[93m",
    "green": "\033[92m",
    "cyan": "\033[96m",
    "blue": "\033[94m",
    "dim": "\033[2m",
    "magenta": "\033[95m",
}

_CATEGORY_COLOR = {
    FailureCategory.COMPILATION_ERROR: "red",
    FailureCategory.TEST_FAILURE: "yellow",
    FailureCategory.FLAKY_TEST: "magenta",
    FailureCategory.RESOURCE_EXHAUSTION: "red",
    FailureCategory.INFRA_FAILURE: "red",
    FailureCategory.DEPENDENCY_FAILURE: "yellow",
    FailureCategory.TIMEOUT: "yellow",
    FailureCategory.UNKNOWN: "cyan",
}

_CATEGORY_ICON = {
    FailureCategory.COMPILATION_ERROR: "✗",
    FailureCategory.TEST_FAILURE: "✗",
    FailureCategory.FLAKY_TEST: "~",
    FailureCategory.RESOURCE_EXHAUSTION: "!",
    FailureCategory.INFRA_FAILURE: "!",
    FailureCategory.DEPENDENCY_FAILURE: "?",
    FailureCategory.TIMEOUT: "⏱",
    FailureCategory.UNKNOWN: "?",
}


def _c(color: str, text: str, bold: bool = False) -> str:
    prefix = _ANSI.get(color, "") + (_ANSI["bold"] if bold else "")
    return f"{prefix}{text}{_ANSI['reset']}"


def _confidence_bar(conf: float, width: int = 20) -> str:
    filled = round(conf * width)
    bar = "█" * filled + "░" * (width - filled)
    color = "green" if conf >= 0.80 else "yellow" if conf >= 0.60 else "red"
    return _c(color, bar) + f" {conf:.0%}"


class TerminalReporter:
    def __init__(self, file=None, no_color: bool = False) -> None:
        self._file = file or sys.stdout
        self._no_color = no_color

    def _print(self, line: str = "") -> None:
        print(line, file=self._file)

    def report(self, triage: TriageReport) -> None:
        c = triage.classification
        cat = c.category
        color = _CATEGORY_COLOR.get(cat, "cyan")
        icon = _CATEGORY_ICON.get(cat, "?")

        self._print()
        self._print(_c("bold", "─" * 60))
        self._print(_c("bold", "  ci-triage  "))
        self._print(_c("bold", "─" * 60))

        header = f"  {icon}  {cat.value.replace('_', ' ').upper()}"
        self._print(_c(color, header, bold=True))

        if triage.build_id:
            self._print(f"  {_c('dim', 'build:')}  {triage.build_id}")
        self._print(f"  {_c('dim', 'source:')} {triage.source.value}")
        self._print(f"  {_c('dim', 'lines:')}  {triage.raw_log_lines:,}")
        self._print(f"  {_c('dim', 'time:')}   {triage.duration_ms:.0f}ms")
        self._print()

        self._print(_c("cyan", "  CONFIDENCE"))
        self._print(f"  {_confidence_bar(c.confidence)}")
        self._print()

        self._print(_c("cyan", "  ROOT CAUSE"))
        self._print(f"  {c.summary}")
        self._print()

        if c.suggested_fix:
            self._print(_c("cyan", "  SUGGESTED FIX"))
            self._print(f"  {c.suggested_fix}")
            self._print()

        if c.failure_sites:
            self._print(_c("cyan", "  FAILURE SITES"))
            for site in c.failure_sites[:5]:
                if site.file and site.line:
                    loc = _c("blue", f"{site.file}:{site.line}")
                    if site.column:
                        loc += _c("dim", f":{site.column}")
                    self._print(f"  {loc}")
                    self._print(f"    {_c('red', site.error_message)}")
                elif site.test_name:
                    self._print(f"  {_c('yellow', site.test_name)}")
                    self._print(f"    {_c('red', site.error_message)}")
                else:
                    self._print(f"  {_c('red', site.error_message)}")
            if len(c.failure_sites) > 5:
                self._print(_c("dim", f"  ... and {len(c.failure_sites) - 5} more"))
            self._print()

        if triage.flaky_test_scores:
            self._print(_c("cyan", "  FLAKY TEST TRACKER"))
            for name, score in sorted(
                triage.flaky_test_scores.items(), key=lambda x: -x[1]
            )[:8]:
                bar = "█" * round(score * 10) + "░" * (10 - round(score * 10))
                color2 = "red" if score >= 0.70 else "yellow" if score >= 0.40 else "green"
                self._print(f"  {_c(color2, bar)} {score:.2f}  {_c('dim', name)}")
            self._print()

        if c.llm_used:
            self._print(_c("dim", "  (analysis: Claude claude-sonnet-4-6)"))
        else:
            self._print(_c("dim", "  (analysis: rule-based)"))

        self._print(_c("bold", "─" * 60))
        self._print()
