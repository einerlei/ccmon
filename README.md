# ccmon

Terminal monitor for Claude Code sessions and subagents in real time. Run `ccmon` to watch your agents.

## Features

- **Real-time monitoring** — watch subagent status, output, and activity as they run
- **Session filtering** — view agents from the current project, a specific project, or all projects
- **Status tracking** — running, completed, interrupted, or unknown states with visual indicators
- **Auto-refresh** — updates every 0.5 seconds without manual intervention
- **Stale expiry** — completed/interrupted agents are automatically removed after 10 minutes of inactivity
- **Manager agent visibility** — shows which specialised agent is currently running in manager-type agents

## Requirements

- Python 3.11+

## Install

### Homebrew (macOS, recommended)

```bash
brew install einerlei/tap/ccmon
```

### pipx (cross-platform)

```bash
pipx install ccmon
```

### pip

```bash
pip install ccmon
```

### Development setup

```bash
git clone https://github.com/einerlei/ccmon.git
cd ccmon
uv sync
uv run ccmon
```

## Usage

```bash
ccmon
ccmon --project /path/to/project
ccmon --all
```

## Key bindings

| Key | Action |
|-----|--------|
| `r` | Manual refresh |
| `q` | Quit |

## Architecture

The monitor is a single-file Python application using the Textual TUI framework.

**Data sources:**
- Sessions: `~/.claude/sessions/*.json` — contains PID, working directory, and session ID
- Subagents: `~/.claude/projects/{project-dir}/{session-id}/subagents/` — per-agent metadata and message logs

**How it works:**
1. Loads active sessions from the sessions directory, filtering by project if specified
2. For each live session, discovers subagents and reads their `.meta.json` (metadata) and `.jsonl` (messages)
3. Infers agent status by analysing message history and checking process liveness
4. Expires completed/interrupted agents after 10 minutes without activity
5. Renders a two-column grid of agent panes with scrolling output
6. Refreshes every 0.5 seconds to keep the view current

## Development

```bash
# Install with dev dependencies
uv sync

# Run tests
uv run pytest -q

# Lint and format
uv run ruff check
uv run ruff format --check

# Run the monitor
ccmon
```

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/my-feature`)
3. Commit your changes (`git commit -am 'Add feature'`)
4. Push to the branch (`git push origin feature/my-feature`)
5. Open a Pull Request

All code must pass `ruff check` and `ruff format --check`. Add tests for new functionality.

## Changelog

See [CHANGELOG.md](CHANGELOG.md)
