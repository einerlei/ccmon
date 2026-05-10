# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Releasing a new version

1. Update `version` in `pyproject.toml`
2. Update `__version__` in `ccmon.py`
3. Add release notes under a new `## [X.Y.Z] - YYYY-MM-DD` section below
4. Commit: `git commit -m "chore: release vX.Y.Z"`
5. Tag: `git tag vX.Y.Z`
6. Push: `git push && git push --tags`

---

## [Unreleased]

## [0.5.3] - 2026-05-10

### Added
- Token usage display: each agent pane shows its cumulative output-token count; the status bar shows the session-wide total

## [0.5.2] - 2026-05-10

### Added
- `-a` as a short alias for `--all`

## [0.5.1] - 2026-05-10

### Fixed
- `--all` now shows sessions that are idle (waiting for user input); previously they disappeared after 5 seconds because Claude's last response was mistaken for a completed/expired agent

## [0.5.0] - 2026-05-05

### Changed
- Renamed package and command from `cctop` to `ccmon`

## [0.4.0] - 2026-05-04

### Added
- Positional `DIR` argument: `cctop .` or `cctop /path/to/project` filters to that directory
- `-p` short alias for `--project`
- Bare `cctop` (no arguments) defaults to the current working directory

### Changed
- `--all` and `--project`/`-p`/positional DIR are now explicitly mutually exclusive with a clear error message

## [0.3.6] - 2026-05-04

### Changed
- `make install` uses `pipx` (the standard for CLI tools); removed redundant `make install-pipx` target

## [0.3.5] - 2026-05-04

### Changed
- `make install` now uses `pip install .`; `make install-pipx` added for pipx-based installs
- Removed `/delegate` skill reference from `CLAUDE.md` (it is a custom skill, not a Claude built-in)

## [0.3.4] - 2026-05-04

### Fixed
- `make install` now gives a clear error if `pipx` is not installed instead of a cryptic make failure
- `make test` coverage target corrected from `--cov=dashboard` to `--cov=cctop`

## [0.3.3] - 2026-05-04

### Fixed
- CI venv cache key now includes `pyproject.toml` so adding/changing dev dependencies (e.g. `pyright`) reliably invalidates the cache

## [0.3.2] - 2026-05-04

### Changed
- Renamed main module from `dashboard.py` to `cctop.py` to align with CLI and project name

## [0.3.1] - 2026-05-04

### Fixed
- Ensured `pyright` is resolvable via `poetry run pyright` in CI by confirming it is
  declared in the `[tool.poetry.group.dev.dependencies]` section; recreating the
  virtual environment resolves stale-venv cache misses that caused "Command not found"

## [0.3.0] - 2026-05-04

### Changed
- **Renamed** project to `cctop`; CLI entrypoint is now `cctop`
- Empty state message updated: "No active Claude Code session" (was "No subagents for project")
- App title updated to "Claude Code Monitor"

### Added
- `Makefile` with `lint`, `format`, `check`, and `test` targets for developer convenience
- `pytest-cov` with 70% coverage floor enforced in CI
- `pyright` type-checking step in CI lint job
- `.pre-commit-config.yaml` with ruff and pyright hooks
- 16 new unit tests covering `_render_output`, `_build_agent_type_lookup`, `_last_skill_call`

### Refactored
- Extracted `_status_display` helper; eliminated duplicated markup logic in `AgentPane`

## [0.2.1] - 2026-05-03

### Added
- Main Claude Code session pane: the parent session now appears alongside its
  subagents, rendered with `◈` symbol and a cyan border (`pane--main` CSS class)

## [0.2.0] - 2026-05-03

### Added
- Test suite with pytest (unit tests for data layer and CLI)
- GitHub Actions CI workflow (lint + test on push/PR to main)
- `__version__` constant in `cctop.py`
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
