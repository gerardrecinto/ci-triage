from __future__ import annotations

import argparse
import datetime
import os
import sys
import time

from ci_triage import __version__
from ci_triage.models import CISource, TriageReport
from ci_triage.parsers import JenkinsParser, GitHubActionsParser, XcodebuildParser
from ci_triage.classifiers import RuleBasedClassifier, LLMClassifier
from ci_triage.reporters import TerminalReporter, SlackReporter, JsonReporter
from ci_triage.tracker import FlakyTestTracker

_SOURCE_MAP = {
    "jenkins": (CISource.JENKINS, JenkinsParser()),
    "github": (CISource.GITHUB_ACTIONS, GitHubActionsParser()),
    "gha": (CISource.GITHUB_ACTIONS, GitHubActionsParser()),
    "xcodebuild": (CISource.XCODEBUILD, XcodebuildParser()),
    "xcode": (CISource.XCODEBUILD, XcodebuildParser()),
}


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ci-triage",
        description="AI-powered CI failure analysis across Jenkins, GitHub Actions, and xcodebuild.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  ci-triage analyze build.log --source jenkins
  ci-triage analyze - --source github      # read from stdin
  ci-triage analyze xcbuild.log --source xcodebuild --llm
  ci-triage analyze build.log --source jenkins --output json
  ci-triage flaky                          # show top flaky tests
""",
    )
    p.add_argument("--version", action="version", version=f"ci-triage {__version__}")

    sub = p.add_subparsers(dest="command", required=True)

    # analyze
    analyze = sub.add_parser("analyze", help="Triage a CI build log")
    analyze.add_argument("log", nargs="?", default="-", help="Log file path (- for stdin)")
    analyze.add_argument(
        "--source", choices=list(_SOURCE_MAP), required=True,
        help="CI source: jenkins | github | gha | xcodebuild | xcode",
    )
    analyze.add_argument(
        "--build-id", default=None, help="Build ID for tracking"
    )
    analyze.add_argument(
        "--llm", action="store_true",
        help="Use Claude for low-confidence or UNKNOWN failures (requires ANTHROPIC_API_KEY)",
    )
    analyze.add_argument(
        "--llm-always", action="store_true",
        help="Always use Claude regardless of rule-based confidence",
    )
    analyze.add_argument(
        "--output", choices=["terminal", "json", "slack"], default="terminal",
        help="Output format",
    )
    analyze.add_argument(
        "--slack-webhook", default=None,
        help="Slack webhook URL (required if --output slack)",
    )
    analyze.add_argument(
        "--no-track", action="store_true",
        help="Do not record failures in the flaky test tracker",
    )
    analyze.add_argument(
        "--db", default="~/.ci-triage/flaky.db",
        help="Flaky test tracker database path",
    )
    analyze.add_argument(
        "--llm-threshold", type=float, default=0.60,
        help="Confidence threshold below which LLM fallback is triggered (default: 0.60)",
    )
    analyze.add_argument(
        "--exit-code", action="store_true",
        help="Exit 1 when a CI failure is detected (useful for blocking pipelines)",
    )

    # flaky
    flaky = sub.add_parser("flaky", help="Show top flaky tests from the tracker")
    flaky.add_argument("--n", type=int, default=20, help="Number of tests to show")
    flaky.add_argument("--db", default="~/.ci-triage/flaky.db")

    return p


def cmd_analyze(args: argparse.Namespace) -> int:
    # Read log
    if args.log == "-":
        log_text = sys.stdin.read()
    else:
        try:
            with open(args.log, encoding="utf-8", errors="replace") as f:
                log_text = f.read()
        except FileNotFoundError:
            print(f"ci-triage: file not found: {args.log}", file=sys.stderr)
            return 1

    source_enum, parser = _SOURCE_MAP[args.source]

    t0 = time.monotonic()

    # Parse
    entries = parser.parse(log_text)
    context = parser.extract_failure_context(entries)

    # Classify
    rule_clf = RuleBasedClassifier()
    result = rule_clf.classify(context)

    if (
        (args.llm_always or (args.llm and result.confidence < args.llm_threshold))
        and os.environ.get("ANTHROPIC_API_KEY")
    ):
        try:
            llm_clf = LLMClassifier()
            result = llm_clf.classify(context)
        except Exception as exc:
            print(f"ci-triage: LLM fallback failed ({exc}), using rule result", file=sys.stderr)

    # Extract failure sites from parser if classifier has none
    if not result.failure_sites and hasattr(parser, "extract_failure_sites"):
        result.failure_sites = parser.extract_failure_sites(context)

    duration_ms = (time.monotonic() - t0) * 1000

    # Flaky test tracking
    tracker = FlakyTestTracker(args.db)
    test_names = [s.test_name for s in result.failure_sites if s.test_name]
    flaky_scores: dict[str, float] = {}

    if test_names:
        flaky_scores = tracker.scores(test_names)
        if not args.no_track:
            for name in test_names:
                tracker.record(name, args.build_id, source_enum.value)

    report = TriageReport(
        build_id=args.build_id,
        source=source_enum,
        timestamp=datetime.datetime.now(datetime.timezone.utc),
        classification=result,
        flaky_test_scores=flaky_scores,
        raw_log_lines=len(entries),
        duration_ms=duration_ms,
    )

    # Report
    if args.output == "json":
        JsonReporter().report(report)
    elif args.output == "slack":
        url = args.slack_webhook or os.environ.get("CI_TRIAGE_SLACK_WEBHOOK")
        if not url:
            print("ci-triage: --slack-webhook or CI_TRIAGE_SLACK_WEBHOOK required", file=sys.stderr)
            return 1
        SlackReporter(url).report(report)
        TerminalReporter().report(report)
    else:
        TerminalReporter().report(report)

    if args.exit_code and result.failure_sites:
        return 1
    return 0


def cmd_flaky(args: argparse.Namespace) -> int:
    tracker = FlakyTestTracker(args.db)
    top = tracker.top_flaky(args.n)
    if not top:
        print("No flaky test history found.")
        return 0
    print(f"\n  Top {len(top)} flaky tests (last 90 days)\n")
    print(f"  {'Score':>6}  Test")
    print("  " + "-" * 55)
    for name, score in top:
        bar = "█" * round(score * 10) + "░" * (10 - round(score * 10))
        print(f"  {score:.2f}   {bar}  {name}")
    print()
    return 0


def main() -> int:
    p = build_parser()
    args = p.parse_args()
    match args.command:
        case "analyze":
            return cmd_analyze(args)
        case "flaky":
            return cmd_flaky(args)
        case _:
            p.print_help()
            return 1


if __name__ == "__main__":
    sys.exit(main())
