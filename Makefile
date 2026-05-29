.PHONY: install test demo demo-jenkins demo-gha demo-xcode demo-flaky clean

install:
	pip install -e ".[dev]"

test:
	pytest tests/ -v --tb=short

test-cov:
	pytest tests/ --cov=ci_triage --cov-report=term-missing

demo: demo-jenkins demo-gha demo-xcode demo-flaky

demo-jenkins:
	@echo "\n=== Jenkins: Java compilation error ==="
	python -m ci_triage.cli analyze tests/fixtures/jenkins_failure.log \
		--source jenkins --build-id "jenkins-build-4821"

demo-gha:
	@echo "\n=== GitHub Actions: pytest failure ==="
	python -m ci_triage.cli analyze tests/fixtures/gha_failure.log \
		--source github --build-id "gha-run-9034"

demo-xcode:
	@echo "\n=== Xcodebuild: Swift compilation + XCTest failure ==="
	python -m ci_triage.cli analyze tests/fixtures/xcodebuild_failure.log \
		--source xcodebuild --build-id "xcode-build-ios27-5512"

demo-flaky:
	@echo "\n=== Flaky test tracker ==="
	python -m ci_triage.cli flaky

demo-json:
	python -m ci_triage.cli analyze tests/fixtures/jenkins_failure.log \
		--source jenkins --output json | python -m json.tool

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null; true
	find . -name "*.pyc" -delete 2>/dev/null; true
	rm -rf .pytest_cache .coverage dist build *.egg-info
