#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
ASSETS_DIR="$REPO_DIR/docs/assets"

cd "$REPO_DIR"

echo ""
echo "ci-triage demo"
echo ""
sleep 0.5

echo "\$ ci-triage analyze tests/fixtures/jenkins_failure.log --source jenkins --build-id jenkins-4821"
sleep 0.4
python -m ci_triage.cli analyze tests/fixtures/jenkins_failure.log --source jenkins --build-id jenkins-4821
sleep 1.0

echo "\$ ci-triage analyze tests/fixtures/xcodebuild_failure.log --source xcodebuild --build-id ios27-5512"
sleep 0.4
python -m ci_triage.cli analyze tests/fixtures/xcodebuild_failure.log --source xcodebuild --build-id ios27-5512
sleep 1.0

echo "\$ ci-triage analyze tests/fixtures/gha_failure.log --source github --build-id gha-9034"
sleep 0.4
python -m ci_triage.cli analyze tests/fixtures/gha_failure.log --source github --build-id gha-9034
sleep 1.5
