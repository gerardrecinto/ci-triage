from __future__ import annotations

import json
import sys
from ci_triage.models import TriageReport


class JsonReporter:
    def __init__(self, file=None) -> None:
        self._file = file or sys.stdout

    def report(self, triage: TriageReport) -> None:
        c = triage.classification
        data = {
            "build_id": triage.build_id,
            "source": triage.source.value,
            "timestamp": triage.timestamp.isoformat(),
            "duration_ms": triage.duration_ms,
            "raw_log_lines": triage.raw_log_lines,
            "classification": {
                "category": c.category.value,
                "confidence": round(c.confidence, 4),
                "summary": c.summary,
                "suggested_fix": c.suggested_fix,
                "llm_used": c.llm_used,
                "failure_sites": [
                    {
                        "file": s.file,
                        "line": s.line,
                        "column": s.column,
                        "test_name": s.test_name,
                        "error_message": s.error_message,
                    }
                    for s in c.failure_sites
                ],
            },
            "flaky_test_scores": triage.flaky_test_scores,
        }
        json.dump(data, self._file, indent=2)
        print(file=self._file)
