# Security Policy

## Reporting a vulnerability

Email gerardrecinto@gmail.com with "ci-triage security" in the subject. Please do not open a public issue for a vulnerability.

Include what you found, how to reproduce it, and the version (`ci-triage --version`). You can expect an acknowledgement within 7 days. This is a one-maintainer project, so a fix timeline depends on severity; I will tell you the plan and credit you in the release notes if you want that.

## Supported versions

Only the latest 1.x release gets security fixes.

## In scope

- A crafted build log that makes the parser run code, write outside the tracker database, or hang.
- Log text or secrets sent to the LLM fallback or to Slack when the operator did not ask for it.
- Problems in the release workflow or the published image.

## Out of scope

- Content of the logs you feed in. Logs often contain tokens, so scrub them before you send them to a hosted model. The rule-based path makes no network calls.
