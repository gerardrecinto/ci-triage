import tempfile
import pytest
from ci_triage.tracker import FlakyTestTracker


@pytest.fixture
def tracker(tmp_path):
    return FlakyTestTracker(tmp_path / "flaky.db")


def test_record_and_score(tracker):
    for i in range(5):
        tracker.record("tests::test_network_timeout", f"build-{i}", "jenkins")
    tracker.record("tests::test_stable", "build-99", "jenkins")

    scores = tracker.scores(["tests::test_network_timeout", "tests::test_stable"])
    assert scores["tests::test_network_timeout"] > scores["tests::test_stable"]
    assert 0.0 < scores["tests::test_network_timeout"] <= 1.0


def test_empty_scores(tracker):
    scores = tracker.scores([])
    assert scores == {}


def test_top_flaky(tracker):
    for i in range(10):
        tracker.record("tests::test_flaky_a", f"b{i}", "jenkins")
    for i in range(3):
        tracker.record("tests::test_flaky_b", f"b{i}", "jenkins")
    tracker.record("tests::test_stable", "b0", "jenkins")

    top = tracker.top_flaky(n=5)
    names = [name for name, _ in top]
    assert names[0] == "tests::test_flaky_a"
    assert "tests::test_flaky_b" in names
    assert all(0.0 <= score <= 1.0 for _, score in top)


def test_no_flaky_history(tracker):
    top = tracker.top_flaky()
    assert top == []


def test_score_capped_at_one(tracker):
    for i in range(100):
        tracker.record("tests::test_always_fails", f"build-{i}", "jenkins")
    scores = tracker.scores(["tests::test_always_fails"])
    assert scores["tests::test_always_fails"] <= 1.0
