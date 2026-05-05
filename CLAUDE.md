# CLAUDE.md — Project instructions for Claude Code

## Version bumps

Every workflow that produces user-facing or tooling changes **must** include a version
bump. Use semantic versioning:

- Breaking change (renamed CLI, removed feature) → minor bump (0.x.0)
- New feature or behaviour change → minor bump (0.x.0)
- Bug fix or internal refactor only → patch bump (0.x.x)

Update both `pyproject.toml` (`version =`) and `ccmon.py` (`__version__ =`), and add a
`## [X.Y.Z] - YYYY-MM-DD` entry to `CHANGELOG.md` following the Keep a Changelog format.

## Smoke-test after changes

After any code change, verify the app starts:

```bash
poetry run ccmon --help
```

Unit tests passing is not sufficient — always run the CLI entrypoint too.
