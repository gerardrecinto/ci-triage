# Changelog

Newest first. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow [Semantic Versioning](https://semver.org/).

## [1.3.0] - 2026-11-06

### Added
- LICENSE, SECURITY.md, CONTRIBUTING.md and this changelog.
- Release assets: the wheel, the sdist and `SHA256SUMS` are attached to each GitHub Release.
- The release image is built for `linux/amd64` and `linux/arm64`, with provenance and an SBOM, and is signed with cosign (keyless).

### Changed
- Workflow actions are pinned to commit SHAs. The release checks that the tag matches `pyproject.toml` and runs CI first.
- CI no longer asks for package write permission.

## [1.2.1] - 2026-10-28

### Added
- A GitHub Pages site with an in-browser demo.

### Fixed
- A directory or unreadable log file gives a one-line error, not a traceback.
- `analyze` with no log on a terminal explains how to pass one instead of waiting on stdin.
- `--output slack` without a webhook fails before anything is written to the tracker.
- Slack or tracker database failures print a warning and the report still prints.
- Duplicate test names in one run are recorded once.
- The Release workflow can be run by hand with a version input.

## [1.2.0] - 2026-08-27

### Changed
- Maintenance release; see the compare view on GitHub.

## [1.1.0] - 2026-08-20

### Fixed
- `--version` reported 0.1.0; the version now lives in one tested place.
- `analyze --exit-code` now gates on the failure category, so failures with no file and line (out of memory, disk full, infrastructure) fail the pipeline.
- The GitHub Actions step-failure pattern now matches real log output.

### Added
- The xcodebuild parser detects codesign failures.

## [1.0.1] - 2026-07-10

### Fixed
- Wheels were built as 0.1.0 whatever the tag; the package version now matches the tag.

### Changed
- README covers badges, Docker pull, and `--exit-code` gating, with a business impact section.

## [1.0.0] - 2026-06-11

### Added
- Rule-based classifier: 7 failure categories, 22 rules, no network needed.
- Optional LLM fallback for ambiguous failures.
- SQLite flaky test tracker with 90-day recurrence scoring.
- `--exit-code` for pipeline gating, and a container image at `ghcr.io/gerardrecinto/ci-triage`.
