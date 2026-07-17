from pathlib import Path
from ci_triage.parsers import JenkinsParser, GitHubActionsParser, XcodebuildParser
from ci_triage.models import CISource

FIXTURES = Path(__file__).parent / "fixtures"


class TestJenkinsParser:
    def setup_method(self):
        self.parser = JenkinsParser()
        self.log = (FIXTURES / "jenkins_failure.log").read_text()

    def test_source(self):
        assert self.parser.source == CISource.JENKINS

    def test_parses_all_lines(self):
        entries = self.parser.parse(self.log)
        assert len(entries) == self.log.count("\n") + (1 if not self.log.endswith("\n") else 0)

    def test_extracts_error_level(self):
        entries = self.parser.parse(self.log)
        errors = [e for e in entries if e.level == "ERROR"]
        assert len(errors) >= 3

    def test_extracts_timestamp(self):
        entries = self.parser.parse(self.log)
        ts_entries = [e for e in entries if e.timestamp is not None]
        assert len(ts_entries) > 0

    def test_failure_context_includes_errors(self):
        entries = self.parser.parse(self.log)
        context = self.parser.extract_failure_context(entries)
        assert any("cannot find symbol" in e.message for e in context)

    def test_extracts_failure_sites(self):
        entries = self.parser.parse(self.log)
        context = self.parser.extract_failure_context(entries)
        sites = self.parser.extract_failure_sites(context)
        assert len(sites) >= 1
        assert sites[0].file is not None
        assert "PipelineOrchestrator.java" in sites[0].file


class TestGitHubActionsParser:
    def setup_method(self):
        self.parser = GitHubActionsParser()
        self.log = (FIXTURES / "gha_failure.log").read_text()

    def test_source(self):
        assert self.parser.source == CISource.GITHUB_ACTIONS

    def test_parses_gha_annotations(self):
        entries = self.parser.parse(self.log)
        errors = [e for e in entries if e.level == "ERROR"]
        assert len(errors) >= 1

    def test_extracts_pytest_failure(self):
        entries = self.parser.parse(self.log)
        sites = self.parser.extract_failure_sites(entries)
        assert any(
            s.test_name and "test_rule_flaky_signal" in s.test_name for s in sites
        )


class TestXcodebuildParser:
    def setup_method(self):
        self.parser = XcodebuildParser()
        self.log = (FIXTURES / "xcodebuild_failure.log").read_text()

    def test_source(self):
        assert self.parser.source == CISource.XCODEBUILD

    def test_extracts_swift_errors(self):
        entries = self.parser.parse(self.log)
        error_entries = [e for e in entries if e.level == "ERROR"]
        assert len(error_entries) >= 3

    def test_failure_context_only_errors(self):
        entries = self.parser.parse(self.log)
        context = self.parser.extract_failure_context(entries)
        assert all(e.level in ("ERROR", "WARNING") for e in context)

    def test_extracts_failure_sites_with_file_line(self):
        entries = self.parser.parse(self.log)
        sites = self.parser.extract_failure_sites(entries)
        file_sites = [s for s in sites if s.file and s.line]
        assert len(file_sites) >= 2

    def test_extracts_test_failure_site(self):
        entries = self.parser.parse(self.log)
        sites = self.parser.extract_failure_sites(entries)
        test_sites = [s for s in sites if s.test_name]
        assert len(test_sites) >= 1
        assert "testAudioDecoderBitIdentical" in test_sites[0].test_name
