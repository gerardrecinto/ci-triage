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
        assert "0 lines parsed" in result.summary

    def test_unknown_for_unrecognized_content(self):
        entries = [LogEntry(1, None, "INFO", "Deploying widget to staging cluster", "")]
        result = self.clf.classify(entries)
        assert result.category == FailureCategory.UNKNOWN
        assert result.confidence == 0.0
        assert "Scanned 1 log line" in result.summary

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


def _classify(parser, text: str):
    entries = parser.parse(text)
    return RuleBasedClassifier().classify(parser.extract_failure_context(entries))


class TestRealWorldErrors:
    def test_xcodebuild_linker_error_without_file_prefix(self):
        log = "ld: symbol(s) not found for architecture arm64\nclang: error: linker command failed with exit code 1\n** BUILD FAILED **\n"
        assert _classify(XcodebuildParser(), log).category == FailureCategory.COMPILATION_ERROR

    def test_xcodebuild_failed_test_case_line(self):
        log = "Test Case '-[AppTests.LoginTests testLogin]' failed (0.123 seconds).\n** TEST FAILED **\n"
        assert _classify(XcodebuildParser(), log).category == FailureCategory.TEST_FAILURE

    def test_missing_provisioning_profile_is_not_unknown(self):
        log = "error: No profiles for 'com.acme.app' were found\n** BUILD FAILED **\n"
        result = _classify(XcodebuildParser(), log)
        assert result.category == FailureCategory.INFRA_FAILURE
        assert "signing" in result.summary.lower()

    def test_missing_swift_module(self):
        log = "/Users/r/A.swift:12:8: error: no such module 'Alamofire'\n** BUILD FAILED **\n"
        assert _classify(XcodebuildParser(), log).category == FailureCategory.DEPENDENCY_FAILURE

    def test_npm_eresolve(self):
        log = "npm ERR! code ERESOLVE\nnpm ERR! ERESOLVE unable to resolve dependency tree\n"
        assert _classify(JenkinsParser(), log).category == FailureCategory.DEPENDENCY_FAILURE

    def test_pip_no_matching_distribution(self):
        log = "ERROR: No matching distribution found for foo\n"
        assert _classify(JenkinsParser(), log).category == FailureCategory.DEPENDENCY_FAILURE

    def test_dns_failure_is_not_an_image_pull(self):
        log = "curl: (6) Could not resolve host: registry.example.com\n"
        result = _classify(JenkinsParser(), log)
        assert result.category == FailureCategory.INFRA_FAILURE
        assert "image pull" not in result.summary.lower()

    def test_numbers_containing_503_do_not_match_gateway_errors(self):
        log = "Compiled 15032 files in 1503s\nERROR: step failed\n"
        assert _classify(JenkinsParser(), log).category == FailureCategory.UNKNOWN

    def test_real_503_still_matches(self):
        log = "ERROR: server returned HTTP 503 Service Unavailable\n"
        assert _classify(JenkinsParser(), log).category == FailureCategory.INFRA_FAILURE
