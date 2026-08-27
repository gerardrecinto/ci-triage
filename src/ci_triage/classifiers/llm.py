from __future__ import annotations

import os
from ci_triage.models import (
    ClassificationResult,
    FailureCategory,
    FailureSite,
    LogEntry,
)

_SYSTEM_PROMPT = """You are a CI/CD failure triage expert.
Given a CI build log excerpt, respond with JSON only (no prose):
{
  "category": "<one of: compilation_error | test_failure | flaky_test | resource_exhaustion | infra_failure | dependency_failure | timeout | unknown>",
  "confidence": <float 0.0-1.0>,
  "summary": "<one sentence root cause>",
  "suggested_fix": "<one actionable fix>",
  "failure_sites": [
    {"file": "<path or null>", "line": <int or null>, "test_name": "<str or null>", "error_message": "<str>"}
  ]
}"""

_MAX_LOG_CHARS = 4000


def _truncate_log(entries: list[LogEntry]) -> str:
    lines = [e.message for e in entries]
    text = "\n".join(lines)
    if len(text) > _MAX_LOG_CHARS:
        half = _MAX_LOG_CHARS // 2
        text = text[:half] + "\n...[truncated]...\n" + text[-half:]
    return text


class LLMClassifier:
    """Claude-powered fallback classifier for low-confidence or UNKNOWN failures."""

    def __init__(self, api_key: str | None = None, model: str = "claude-sonnet-4-6") -> None:
        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self._model = model

    def classify(self, entries: list[LogEntry]) -> ClassificationResult:
        import anthropic
        import json

        log_text = _truncate_log(entries)

        client = anthropic.Anthropic(api_key=self._api_key)
        response = client.messages.create(
            model=self._model,
            max_tokens=512,
            system=[
                {
                    "type": "text",
                    "text": _SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": log_text}],
        )

        raw = response.content[0].text.strip()
        # Strip markdown code fences if Claude wraps in ```json
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]

        data: dict = json.loads(raw)

        sites: list[FailureSite] = []
        for s in data.get("failure_sites", []):
            sites.append(FailureSite(
                file=s.get("file"),
                line=s.get("line"),
                column=None,
                test_name=s.get("test_name"),
                error_message=s.get("error_message", ""),
            ))

        return ClassificationResult(
            category=FailureCategory(data.get("category", "unknown")),
            confidence=float(data.get("confidence", 0.5)),
            failure_sites=sites,
            summary=data.get("summary", "LLM triage complete"),
            suggested_fix=data.get("suggested_fix"),
            llm_used=True,
        )
