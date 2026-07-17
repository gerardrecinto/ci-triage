from __future__ import annotations

import json
import urllib.request
from ci_triage.models import FailureCategory, TriageReport

_EMOJI = {
    FailureCategory.COMPILATION_ERROR: ":red_circle:",
    FailureCategory.TEST_FAILURE: ":x:",
    FailureCategory.FLAKY_TEST: ":large_yellow_circle:",
    FailureCategory.RESOURCE_EXHAUSTION: ":exclamation:",
    FailureCategory.INFRA_FAILURE: ":rotating_light:",
    FailureCategory.DEPENDENCY_FAILURE: ":warning:",
    FailureCategory.TIMEOUT: ":hourglass:",
    FailureCategory.UNKNOWN: ":grey_question:",
}


class SlackReporter:
    def __init__(self, webhook_url: str) -> None:
        self._url = webhook_url

    def report(self, triage: TriageReport) -> None:
        c = triage.classification
        emoji = _EMOJI.get(c.category, ":grey_question:")
        category_label = c.category.value.replace("_", " ").title()

        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{emoji} CI Failure: {category_label}",
                },
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Build:*\n{triage.build_id or 'unknown'}"},
                    {"type": "mrkdwn", "text": f"*Source:*\n{triage.source.value}"},
                    {"type": "mrkdwn", "text": f"*Confidence:*\n{c.confidence:.0%}"},
                    {"type": "mrkdwn", "text": f"*Log lines:*\n{triage.raw_log_lines:,}"},
                ],
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Root cause:*\n{c.summary}",
                },
            },
        ]
        if c.suggested_fix:
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Suggested fix:*\n{c.suggested_fix}",
                },
            })
        if c.failure_sites:
            sites_text = "\n".join(
                f"• `{s.file}:{s.line}` — {s.error_message}"
                if s.file else f"• `{s.test_name or 'unknown'}` — {s.error_message}"
                for s in c.failure_sites[:5]
            )
            blocks.append({
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*Failure sites:*\n{sites_text}"},
            })
        if triage.flaky_test_scores:
            high_flaky = [
                f"`{name}` ({score:.2f})"
                for name, score in triage.flaky_test_scores.items()
                if score >= 0.70
            ]
            if high_flaky:
                blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": ":warning: *High-recurrence flaky tests:*\n" + "\n".join(high_flaky),
                    },
                })

        payload = json.dumps({"blocks": blocks}).encode()
        req = urllib.request.Request(
            self._url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status != 200:
                raise RuntimeError(f"Slack webhook returned {resp.status}")
