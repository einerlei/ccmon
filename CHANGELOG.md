# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Releasing a new version

1. Update `version` in `pyproject.toml`
2. Update `__version__` in `dashboard.py`
3. Add release notes under a new `## [X.Y.Z] - YYYY-MM-DD` section below
4. Commit: `git commit -m "chore: release vX.Y.Z"`
5. Tag: `git tag vX.Y.Z`
6. Push: `git push && git push --tags`

---

## [Unreleased]

## [0.2.0] - 2026-05-03

### Added
- Test suite with pytest (unit tests for data layer and CLI)
- GitHub Actions CI workflow (lint + test on push/PR to main)
- `__version__` constant in `dashboard.py`
- Expanded README with architecture overview, dev setup, and contributing guide

### Changed
- Code quality improvements based on review (type annotations, error handling)

## [0.1.0] - 2026-04-01

### Added
- Initial release: terminal TUI for monitoring Claude Code subagents
- Real-time auto-refresh (0.5s interval)
- Session filtering by project directory (`--project`, `--all` flags)
- Status tracking: running, completed, interrupted, unknown
- Stale agent expiry (10-minute timeout for non-running agents)
- 2-column grid layout with Rich-styled message history per agent
