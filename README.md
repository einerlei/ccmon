# Claude Agents Dashboard

Terminal TUI for monitoring Claude Code subagents in real time.

## Install

```bash
poetry install
```

## Usage

```bash
# Show agents for the current directory (default)
poetry run agents-dashboard

# Show agents for a specific project
poetry run agents-dashboard --project /path/to/project

# Show agents from all projects
poetry run agents-dashboard --all
```

## Key bindings

| Key | Action |
|-----|--------|
| `r` | Manual refresh |
| `q` | Quit |
