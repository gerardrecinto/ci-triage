import datetime
import io

from ci_triage.models import CISource, ClassificationResult, FailureCategory, TriageReport
from ci_triage.reporters import TerminalReporter


def _report(confidence: float, summary: str) -> TriageReport:
    return TriageReport(
        build_id="b1",
        source=CISource.JENKINS,
        timestamp=datetime.datetime.now(datetime.timezone.utc),
        classification=ClassificationResult(
            category=FailureCategory.UNKNOWN,
            confidence=confidence,
            failure_sites=[],
            summary=summary,
            suggested_fix="Configure ANTHROPIC_API_KEY and re-run with --llm.",
        ),
    )


class TestTerminalReporterConfidence:
    def test_zero_confidence_shows_needs_review_not_bare_percent(self):
        buf = io.StringIO()
        TerminalReporter(file=buf).report(_report(0.0, "No log content to analyze (0 lines parsed)"))
        out = buf.getvalue()
        assert "NEEDS REVIEW" in out
        assert "0%" not in out

    def test_nonzero_confidence_still_shows_bar(self):
        buf = io.StringIO()
        TerminalReporter(file=buf).report(_report(0.75, "Compilation error"))
        out = buf.getvalue()
        assert "75%" in out
        assert "NEEDS REVIEW" not in out
