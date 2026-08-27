from pathlib import Path
from ci_triage.classifiers import RuleBasedClassifier
from ci_triage.models import FailureCategory, LogEntry
from ci_triage.parsers import JenkinsParser, GitHubActionsParser, XcodebuildParser

FIXTURES = Path(__file__).parent / "fixtures"


def _entries_from_fixture(parser, name: str) -> list[LogEntry]:
    log = (FIXTURES / name).read_text()
    entries = parser.parse(log)
    return parser.extract_failure_context(entries)


class TestRuleBasedClassifier:
    def setup_method(self):
        self.clf = RuleBasedClassifier()

    def test_jenkins_compilation_error(self):
        context = _entries_from_fixture(JenkinsParser(), "jenkins_failure.log")
        result = self.clf.classify(context)
        assert result.category == FailureCategory.COMPILATION_ERROR
        assert result.confidence >= 0.85
        assert not result.llm_used

    def test_gha_test_failure(self):
        context = _entries_from_fixture(GitHubActionsParser(), "gha_failure.log")
        result = self.clf.classify(context)
        assert result.category == FailureCategory.TEST_FAILURE
        assert result.confidence >= 0.80

    def test_xcodebuild_compilation_error(self):
        context = _entries_from_fixture(XcodebuildParser(), "xcodebuild_failure.log")
        result = self.clf.classify(context)
        assert result.category == FailureCategory.COMPILATION_ERROR
        assert result.confidence >= 0.85

    def test_oom_detection(self):
        entries = [LogEntry(1, None, "ERROR", "java.lang.OutOfMemoryError: Java heap space", "")]
        result = self.clf.classify(entries)
        assert result.category == FailureCategory.RESOURCE_EXHAUSTION

    def test_flaky_signal(self):
        entries = [LogEntry(1, None, None, "flaky test intermittent connection refused retry attempt", "")]
        result = self.clf.classify(entries)
        assert result.category in (FailureCategory.FLAKY_TEST, FailureCategory.INFRA_FAILURE)

    def test_timeout_detection(self):
        entries = [LogEntry(1, None, "ERROR", "Build timed out after 3600 seconds", "")]
        result = self.clf.classify(entries)
        assert result.category == FailureCategory.TIMEOUT

    def test_infra_docker_pull_failure(self):
        entries = [LogEntry(1, None, "ERROR", "docker pull registry.example.com/image:latest - manifest unknown", "")]
        result = self.clf.classify(entries)
        assert result.category == FailureCategory.INFRA_FAILURE

    def test_unknown_for_empty(self):
        result = self.clf.classify([])
        assert result.category == FailureCategory.UNKNOWN
        assert result.confidence == 0.0
        assert "ANTHROPIC_API_KEY" in result.suggested_fix

    def test_jenkins_script_security_error(self):
        entries = [LogEntry(1, None, "ERROR", "org.jenkinsci.plugins.scriptsecurity.sandbox.RejectedAccessException: Scripts not permitted to use method", "")]
        result = self.clf.classify(entries)
        assert result.category == FailureCategory.INFRA_FAILURE
        assert result.confidence >= 0.88
        assert "Script Approval" in result.suggested_fix

    def test_permission_denied_error(self):
        entries = [LogEntry(1, None, "ERROR", "chmod: cannot access '/var/jenkins/workspace/test': Permission denied", "")]
        result = self.clf.classify(entries)
        assert result.category == FailureCategory.INFRA_FAILURE
        assert result.confidence >= 0.88
        assert "credentials" in result.suggested_fix.lower()

    def test_suggested_fix_populated(self):
        entries = [LogEntry(1, None, "ERROR", "java.lang.OutOfMemoryError: GC overhead limit exceeded", "")]
        result = self.clf.classify(entries)
        assert result.suggested_fix is not None
        assert len(result.suggested_fix) > 0
