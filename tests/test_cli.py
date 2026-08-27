import json
import tomllib
from pathlib import Path
from ci_triage import __version__
from ci_triage.cli import build_parser, cmd_analyze, cmd_flaky
from ci_triage.tracker import FlakyTestTracker

FIXTURES = Path(__file__).parent / "fixtures"
REPO_ROOT = Path(__file__).parent.parent


def test_version_matches_pyproject():
    # Regression: __init__.py.__version__ silently drifted from the
    # pyproject.toml version (1.0.2 vs 0.1.0) because bumping one didn't
    # bump the other. Keep them locked together.
    data = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text())
    assert __version__ == data["project"]["version"]


def _run(tmp_path, log_path: str, source: str, extra: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(
        ["analyze", log_path, "--source", source, "--db", str(tmp_path / "flaky.db"),
         "--no-track", "--exit-code", *(extra or [])]
    )
    return cmd_analyze(args)


class TestExitCode:
    def test_exit_1_on_compilation_error(self, tmp_path):
        # Regression: file:line failure sites present, should still gate.
        assert _run(tmp_path, str(FIXTURES / "jenkins_failure.log"), "jenkins") == 1

    def test_exit_1_on_resource_exhaustion_without_failure_sites(self, tmp_path, capsys):
        # OOM/disk logs rarely carry file:line failure sites, but they are
        # still a real CI failure and --exit-code must gate on them too.
        log = tmp_path / "oom.log"
        log.write_text(
            "2026-08-20T01:00:00Z [ERROR] No space left on device\n"
            "2026-08-20T01:00:01Z BUILD FAILURE\n"
        )
        assert _run(tmp_path, str(log), "jenkins") == 1

    def test_exit_0_on_clean_log(self, tmp_path):
        log = tmp_path / "clean.log"
        log.write_text("2026-08-20T01:00:00Z [INFO] BUILD SUCCESS\n")
        assert _run(tmp_path, str(log), "jenkins") == 0

    def test_no_exit_code_flag_always_zero(self, tmp_path):
        parser = build_parser()
        log = tmp_path / "oom.log"
        log.write_text("2026-08-20T01:00:00Z [ERROR] No space left on device\n")
        args = parser.parse_args(
            ["analyze", str(log), "--source", "jenkins", "--db", str(tmp_path / "flaky.db"), "--no-track"]
        )
        assert cmd_analyze(args) == 0

    def test_llm_flag_without_api_key_warns(self, tmp_path, monkeypatch, capsys):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        log = tmp_path / "perm.log"
        log.write_text("2026-08-20T01:00:00Z [ERROR] Unrecognized custom failure\n")
        parser = build_parser()
        args = parser.parse_args(
            ["analyze", str(log), "--source", "jenkins", "--llm-always", "--db", str(tmp_path / "flaky.db"), "--no-track"]
        )
        cmd_analyze(args)
        err = capsys.readouterr().err
        assert "ANTHROPIC_API_KEY is missing" in err


class TestFlakyCommand:
    def _tracker(self, tmp_path) -> FlakyTestTracker:
        return FlakyTestTracker(tmp_path / "flaky.db")

    def test_json_output_marks_quarantine_candidates(self, tmp_path, capsys):
        tr = self._tracker(tmp_path)
        for i in range(10):
            tr.record("tests::test_always_fails", f"b{i}", "jenkins")

        parser = build_parser()
        args = parser.parse_args(["flaky", "--db", str(tmp_path / "flaky.db"), "--output", "json"])
        cmd_flaky(args)
        out = json.loads(capsys.readouterr().out)
        assert out["quarantine_threshold"] == 0.70
        assert out["tests"][0]["quarantine_candidate"] is True

    def test_exit_code_1_when_quarantine_candidate_exists(self, tmp_path):
        tr = self._tracker(tmp_path)
        for i in range(10):
            tr.record("tests::test_always_fails", f"b{i}", "jenkins")

        parser = build_parser()
        args = parser.parse_args(["flaky", "--db", str(tmp_path / "flaky.db"), "--exit-code"])
        assert cmd_flaky(args) == 1

    def test_exit_code_0_when_no_quarantine_candidate(self, tmp_path):
        # Three tests, each failing on its own distinct build IDs so no
        # single test dominates the denominator: 3/9 = 0.33, well under 0.70.
        tr = self._tracker(tmp_path)
        for name in ("tests::test_a", "tests::test_b", "tests::test_c"):
            for i in range(3):
                tr.record(name, f"{name}-b{i}", "jenkins")

        parser = build_parser()
        args = parser.parse_args(["flaky", "--db", str(tmp_path / "flaky.db"), "--exit-code"])
        assert cmd_flaky(args) == 0

    def test_terminal_output_flags_quarantine_candidate(self, tmp_path, capsys):
        tr = self._tracker(tmp_path)
        for i in range(10):
            tr.record("tests::test_always_fails", f"b{i}", "jenkins")

        parser = build_parser()
        args = parser.parse_args(["flaky", "--db", str(tmp_path / "flaky.db")])
        cmd_flaky(args)
        assert "quarantine candidate" in capsys.readouterr().out
