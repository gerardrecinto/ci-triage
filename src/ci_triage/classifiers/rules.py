from __future__ import annotations

import re
from dataclasses import dataclass
from ci_triage.models import (
    ClassificationResult,
    FailureCategory,
    FailureSite,
    LogEntry,
)


@dataclass(slots=True, frozen=True)
class _Rule:
    pattern: re.Pattern[str]
    category: FailureCategory
    weight: float
    summary_template: str
    fix_template: str | None


_RULES: list[_Rule] = [
    # Permission and Authorization failures
    _Rule(
        re.compile(r"(ScriptSecurityException|script.*not approved|RejectedAccessException|scripts not permitted)", re.I),
        FailureCategory.INFRA_FAILURE, 0.90,
        "Jenkins script security approval required",
        "Approve the pending script in Jenkins (Manage Jenkins > In-process Script Approval). If pipeline logic is blocked by custom credentials, configure ANTHROPIC_API_KEY and run with --llm.",
    ),
    _Rule(
        re.compile(r"(permission denied|access denied|operation not permitted|EACCES|EPERM|403 Forbidden|401 Unauthorized|HTTP 403|HTTP 401)", re.I),
        FailureCategory.INFRA_FAILURE, 0.88,
        "Permission or authentication failure in CI pipeline",
        "Check user/agent credentials, file permissions, SSH keys, or access tokens. Configure ANTHROPIC_API_KEY (Claude Code API key) and re-run with --llm for AI root cause analysis.",
    ),
    # Compilation errors
    _Rule(
        re.compile(r"error: .*(cannot find|unresolved identifier|type .* has no member|undeclared identifier)", re.I),
        FailureCategory.COMPILATION_ERROR, 0.9,
        "Swift/ObjC compilation failed: unresolved symbol or type error",
        "Check import statements and ensure the symbol is accessible in the current module/scope.",
    ),
    _Rule(
        re.compile(r"(SyntaxError|IndentationError|NameError|ImportError|ModuleNotFoundError):", re.I),
        FailureCategory.COMPILATION_ERROR, 0.88,
        "Python syntax or import error",
        "Fix the syntax error or ensure the package is installed in the CI virtualenv.",
    ),
    _Rule(
        re.compile(r"\[ERROR\] .+\.java:\d+: error:", re.I),
        FailureCategory.COMPILATION_ERROR, 0.92,
        "Java/Kotlin compilation failed",
        "Check the compiler error at the referenced file:line.",
    ),
    _Rule(
        re.compile(r"e: .+\.kt:\d+:\d+: error:", re.I),
        FailureCategory.COMPILATION_ERROR, 0.92,
        "Kotlin compilation failed",
        "Fix the Kotlin type or syntax error at the referenced file:line:col.",
    ),
    _Rule(
        re.compile(r"ld: .*(library not found|framework not found|symbol.* not found)", re.I),
        FailureCategory.COMPILATION_ERROR, 0.87,
        "Linker error: missing library or symbol",
        "Verify framework search paths and check that all linked libraries are present in the build environment.",
    ),
    # Test failures
    _Rule(
        re.compile(r"^FAILED\s+\S+::", re.M),
        FailureCategory.TEST_FAILURE, 0.93,
        "pytest test case failed",
        "Run the failing test locally with -s -v to capture assertion output.",
    ),
    _Rule(
        re.compile(r"Test Case '.+?' failed \([0-9.]+ seconds\)"),
        FailureCategory.TEST_FAILURE, 0.93,
        "XCTest case failed",
        "Run the test in Xcode with the same scheme and check the XCResult bundle for stack trace.",
    ),
    _Rule(
        re.compile(r"FAILED \d+ tests? in \S+"),
        FailureCategory.TEST_FAILURE, 0.85,
        "Test suite reported failures",
        "Check the test output above for individual assertion details.",
    ),
    _Rule(
        re.compile(r"AssertionError", re.I),
        FailureCategory.TEST_FAILURE, 0.82,
        "Assertion failed in test",
        "Check assertion value vs expected. Add pytest -s to see print() output.",
    ),
    # Flaky test signals
    _Rule(
        re.compile(r"(flaky|intermittent|timeout.*retry|retry.*attempt)", re.I),
        FailureCategory.FLAKY_TEST, 0.75,
        "Potential flaky test: retry or intermittent keywords detected",
        "Track recurrence across builds. If score > 0.7, quarantine and file a flakiness bug.",
    ),
    _Rule(
        re.compile(r"connection (refused|reset|timed out).*test", re.I),
        FailureCategory.FLAKY_TEST, 0.70,
        "Test likely flaky due to network dependency",
        "Mock network calls in unit tests. For integration tests, add retry with exponential backoff.",
    ),
    # Resource exhaustion
    _Rule(
        re.compile(r"(out of memory|OOMKilled|java\.lang\.OutOfMemoryError|MemoryError)", re.I),
        FailureCategory.RESOURCE_EXHAUSTION, 0.92,
        "OOM: build agent or test process ran out of memory",
        "Increase memory limit for the CI agent, or reduce parallelism (--workers/-n flags).",
    ),
    _Rule(
        re.compile(r"(disk space|no space left|No space left on device)", re.I),
        FailureCategory.RESOURCE_EXHAUSTION, 0.94,
        "Disk exhaustion on CI agent",
        "Clean artifact cache before build. Check if DerivedData / .gradle cache is unbounded.",
    ),
    _Rule(
        re.compile(r"(CPU throttl|resource limit exceeded|cgroup|ulimit)", re.I),
        FailureCategory.RESOURCE_EXHAUSTION, 0.80,
        "CPU or cgroup resource limit hit",
        "Check agent resource limits. Consider increasing CPU quota or reducing build concurrency.",
    ),
    # Infrastructure failures
    _Rule(
        re.compile(r"(connection refused|ECONNREFUSED|504|502|503|gateway timeout)", re.I),
        FailureCategory.INFRA_FAILURE, 0.82,
        "Network/gateway failure: upstream dependency unreachable",
        "Check if the target service is healthy. This is likely an infrastructure issue, not a code bug.",
    ),
    _Rule(
        re.compile(r"(docker pull|registry|image not found|manifest unknown)", re.I),
        FailureCategory.INFRA_FAILURE, 0.85,
        "Container image pull failure",
        "Verify the image tag exists in the registry and the agent has pull credentials.",
    ),
    _Rule(
        re.compile(r"(kubectl|kubernetes|k8s).*(failed|error|timeout)", re.I),
        FailureCategory.INFRA_FAILURE, 0.80,
        "Kubernetes deployment or health check failed",
        "Check pod events: kubectl describe pod / kubectl get events -n <namespace>.",
    ),
    _Rule(
        re.compile(r"(git clone|git fetch|git lfs|smudge).*(failed|error|timeout|403|401)", re.I),
        FailureCategory.INFRA_FAILURE, 0.88,
        "Git or LFS fetch failure",
        "Check SCM credentials, LFS server availability, and network proxy config on the agent.",
    ),
    # Dependency failures
    _Rule(
        re.compile(r"(requirements.txt|pip install|poetry install|npm install|yarn install).*(failed|error)", re.I),
        FailureCategory.DEPENDENCY_FAILURE, 0.85,
        "Dependency installation failed",
        "Check package version constraints, private registry access, and index reachability.",
    ),
    _Rule(
        re.compile(r"(Could not resolve|dependency.*not found|artifact.*missing)", re.I),
        FailureCategory.DEPENDENCY_FAILURE, 0.82,
        "Artifact or dependency resolution failed",
        "Verify the artifact is published in the artifact repository or Maven Central and the build has access.",
    ),
    # Timeout
    _Rule(
        re.compile(r"(build.*timed? ?out|timeout.*exceeded|deadline exceeded|signal: killed)", re.I),
        FailureCategory.TIMEOUT, 0.88,
        "Build or step timed out",
        "Check for an infinite loop, hung process, or genuinely slow test. Increase timeout or add parallelism.",
    ),
]


def _top_category(hits: list[tuple[_Rule, str]]) -> tuple[FailureCategory, float]:
    if not hits:
        return FailureCategory.UNKNOWN, 0.0
    scores: dict[FailureCategory, float] = {}
    for rule, _ in hits:
        scores[rule.category] = max(scores.get(rule.category, 0.0), rule.weight)
    best = max(scores, key=lambda c: scores[c])
    return best, scores[best]


class RuleBasedClassifier:
    def classify(self, entries: list[LogEntry]) -> ClassificationResult:
        combined = "\n".join(e.message for e in entries)
        hits: list[tuple[_Rule, str]] = []
        for rule in _RULES:
            m = rule.pattern.search(combined)
            if m:
                hits.append((rule, m.group(0)))

        category, confidence = _top_category(hits)

        if hits:
            primary_rule = max(hits, key=lambda h: h[0].weight)
            summary = primary_rule[0].summary_template
            fix = primary_rule[0].fix_template
        else:
            summary = "No matching failure pattern found"
            fix = "No matching rule found. Configure your ANTHROPIC_API_KEY (Claude Code API key) and re-run with --llm for AI-powered failure triage."

        failure_sites: list[FailureSite] = []
        return ClassificationResult(
            category=category,
            confidence=confidence,
            failure_sites=failure_sites,
            summary=summary,
            suggested_fix=fix,
            llm_used=False,
        )

        failure_sites: list[FailureSite] = []
        return ClassificationResult(
            category=category,
            confidence=confidence,
            failure_sites=failure_sites,
            summary=summary,
            suggested_fix=fix,
            llm_used=False,
        )
