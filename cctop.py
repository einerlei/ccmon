#!/usr/bin/env python3
"""cctop — monitor running Claude Code sessions and subagents."""

from __future__ import annotations

import argparse
import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path

from rich.markup import escape
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Grid, ScrollableContainer
from textual.widget import Widget
from textual.widgets import Footer, Header, Static

__version__ = "0.3.4"

logger = logging.getLogger(__name__)

# ─── Constants ────────────────────────────────────────────────────────────────

CLAUDE_DIR = Path.home() / ".claude"
SESSIONS_DIR = CLAUDE_DIR / "sessions"
PROJECTS_DIR = CLAUDE_DIR / "projects"
REFRESH_INTERVAL = 0.5
STALE_THRESHOLD_SECONDS = 2
EXPIRE_SECONDS = 5
OUTPUT_LINES = 10

STATUS_STYLE: dict[str, tuple[str, str]] = {
    "running": ("green", "●"),
    "completed": ("dim", "○"),
    "interrupted": ("yellow", "◐"),
    "unknown": ("dim", "?"),
    "main": ("cyan", "◈"),
}

# ─── Data layer ───────────────────────────────────────────────────────────────


@dataclass
class SessionInfo:
    pid: int
    session_id: str
    cwd: str
    is_alive: bool


@dataclass
class AgentData:
    agent_id: str
    description: str
    agent_type: str
    session: SessionInfo
    status: str
    messages: list[dict] = field(default_factory=list)
    started_at: float = 0.0
    jsonl_mtime: float = 0.0

    @property
    def key(self) -> str:
        return f"{self.session.session_id}:{self.agent_id}"


def _is_pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _cwd_to_project_dir(cwd: str) -> str:
    return cwd.replace("/", "-")


def _load_sessions(project_filter: Path | None = None) -> list[SessionInfo]:
    """Load all sessions, optionally filtering to those whose cwd matches *project_filter*."""
    if not SESSIONS_DIR.exists():
        return []
    sessions = []
    for f in SESSIONS_DIR.glob("*.json"):
        try:
            data = json.loads(f.read_text())
            pid = data.get("pid")
            session_id = data.get("sessionId", "")
            cwd = data.get("cwd", "")
            if not (pid and session_id):
                continue
            if project_filter is not None:
                # Resolve both to absolute paths for an exact match.
                if Path(cwd).resolve() != project_filter:
                    continue
            sessions.append(
                SessionInfo(
                    pid=pid,
                    session_id=session_id,
                    cwd=cwd,
                    is_alive=_is_pid_alive(pid),
                )
            )
        except Exception as e:
            logger.debug("Failed to load session %s: %s", f, e)
            continue
    return sessions


def _infer_status(messages: list[dict], session_alive: bool, jsonl_mtime: float = 0.0) -> str:
    if not messages:
        return "unknown"
    is_stale = time.time() - jsonl_mtime > STALE_THRESHOLD_SECONDS
    last = messages[-1]
    if last.get("type") == "assistant":
        content = last.get("message", {}).get("content", [])
        if content and isinstance(content[-1], dict) and content[-1].get("type") == "tool_use":
            if not session_alive or is_stale:
                return "interrupted"
            return "running"
        return "completed"
    if last.get("type") == "user":
        if not session_alive or is_stale:
            return "interrupted"
        return "running"
    return "unknown"


def _load_messages(path: Path) -> list[dict]:
    try:
        return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    except Exception as e:
        logger.debug("Failed to load messages from %s: %s", path, e)
        return []


def _build_agent_type_lookup(session_id: str, project_dir: str) -> dict[str, str]:
    """Parse the parent session JSONL and return a mapping of description -> subagent_type.

    Claude Code writes the Agent tool call (with both ``description`` and
    ``subagent_type``) into the *session* JSONL (not the subagent JSONL).  The
    ``description`` value is also stored verbatim in every subagent's
    ``.meta.json``, so we can use it as the join key.
    """
    session_jsonl = PROJECTS_DIR / project_dir / f"{session_id}.jsonl"
    if not session_jsonl.exists():
        return {}
    lookup: dict[str, str] = {}
    try:
        for line in session_jsonl.read_text().splitlines():
            if not line.strip():
                continue
            entry = json.loads(line)
            msg = entry.get("message", {})
            content = msg.get("content", [])
            if not isinstance(content, list):
                continue
            for item in content:
                if (
                    isinstance(item, dict)
                    and item.get("type") == "tool_use"
                    and item.get("name") == "Agent"
                ):
                    desc = item.get("input", {}).get("description", "")
                    st = item.get("input", {}).get("subagent_type", "")
                    if desc and st:
                        lookup[desc] = st
    except Exception as e:
        logger.debug("Failed to build agent type lookup for session %s: %s", session_id, e)
    return lookup


def _last_skill_call(messages: list[dict]) -> str | None:
    """Return the name of the most recently invoked Skill, or None."""
    last: str | None = None
    for msg in messages:
        content = msg.get("message", {}).get("content", [])
        if not isinstance(content, list):
            continue
        for item in content:
            if (
                isinstance(item, dict)
                and item.get("type") == "tool_use"
                and item.get("name") == "Skill"
            ):
                skill_name = item.get("input", {}).get("skill", "")
                if skill_name:
                    last = skill_name
    return last


def _load_agents_for_session(session: SessionInfo) -> list[AgentData]:
    project_dir = _cwd_to_project_dir(session.cwd)
    subagents_dir = PROJECTS_DIR / project_dir / session.session_id / "subagents"
    if not subagents_dir.exists():
        return []

    # Build a lookup from description -> subagent_type from the parent session JSONL.
    type_lookup = _build_agent_type_lookup(session.session_id, project_dir)

    agents = []
    for meta_file in subagents_dir.glob("agent-*.meta.json"):
        try:
            meta = json.loads(meta_file.read_text())
            agent_id = meta_file.name.removeprefix("agent-").removesuffix(".meta.json")
            jsonl_path = meta_file.with_name(f"agent-{agent_id}.jsonl")
            try:
                jsonl_mtime = jsonl_path.stat().st_mtime
                messages = _load_messages(jsonl_path)
            except FileNotFoundError:
                jsonl_mtime = 0.0
                messages = []
            meta_description = meta.get("description", "")
            # Prefer the subagent_type recorded in the parent session's Agent call;
            # fall back to the agentType stored in .meta.json.
            agent_type = type_lookup.get(meta_description) or meta.get("agentType", "unknown")
            # For manager-type agents, surface the last Skill they invoked so the
            # user can see which specialised agent they are currently running.
            if agent_type == "manager":
                skill = _last_skill_call(messages)
                if skill:
                    agent_type = f"manager → {skill}"
            agents.append(
                AgentData(
                    agent_id=agent_id,
                    description=meta_description or agent_type,
                    agent_type=agent_type,
                    session=session,
                    status=_infer_status(messages, session.is_alive, jsonl_mtime),
                    messages=messages,
                    started_at=meta_file.stat().st_mtime,
                    jsonl_mtime=jsonl_mtime,
                )
            )
        except Exception as e:
            logger.debug("Failed to load agent from %s: %s", meta_file, e)
            continue
    return agents


def _load_main_thread(session: SessionInfo) -> AgentData | None:
    """Load the main Claude Code session thread as an AgentData entry."""
    project_dir = _cwd_to_project_dir(session.cwd)
    jsonl_path = PROJECTS_DIR / project_dir / f"{session.session_id}.jsonl"
    try:
        jsonl_mtime = jsonl_path.stat().st_mtime
        messages = _load_messages(jsonl_path)
    except FileNotFoundError:
        return None
    status = _infer_status(messages, session_alive=session.is_alive, jsonl_mtime=jsonl_mtime)
    return AgentData(
        agent_id="__main__",
        description=f"Main — {Path(session.cwd).name}",
        agent_type="main",
        session=session,
        status=status,
        messages=messages,
        started_at=jsonl_mtime,
        jsonl_mtime=jsonl_mtime,
    )


def load_all_agents(project_filter: Path | None = None) -> list[AgentData]:
    """Return agents from live sessions, sorted newest-first, with stale finished agents removed.

    Agents whose status is completed/interrupted/unknown and whose last activity
    (jsonl mtime, or meta mtime as fallback) is older than EXPIRE_SECONDS are
    excluded.  Running agents are never excluded.
    """
    agents: list[AgentData] = []
    for session in _load_sessions(project_filter):
        if not session.is_alive:
            continue
        main_thread = _load_main_thread(session)
        session_agents = _load_agents_for_session(session)
        if main_thread is not None:
            agents.append(main_thread)
        agents.extend(session_agents)

    cutoff = time.time() - EXPIRE_SECONDS
    filtered: list[AgentData] = []
    for agent in agents:
        if agent.status == "running":
            filtered.append(agent)
            continue
        last_activity = agent.jsonl_mtime or agent.started_at
        if last_activity >= cutoff:
            filtered.append(agent)

    filtered.sort(key=lambda a: a.started_at, reverse=True)
    return filtered


# ─── Output rendering ─────────────────────────────────────────────────────────


def _render_output(messages: list[dict]) -> list[tuple[str, str]]:
    lines: list[tuple[str, str]] = []
    for msg in messages:
        if msg.get("type") == "assistant":
            for c in msg.get("message", {}).get("content", []):
                if not isinstance(c, dict):
                    continue
                if c.get("type") == "text":
                    for raw in c.get("text", "").splitlines():
                        raw = raw.strip()
                        if raw:
                            lines.append(("", raw[:140]))
                elif c.get("type") == "tool_use":
                    name = c.get("name", "")
                    inp = c.get("input", {})
                    if name == "Bash":
                        lines.append(("dim", f"$ {inp.get('command', '')[:120]}"))
                    else:
                        lines.append(("dim", f"→ {name}"))
        elif msg.get("type") == "user":
            content = msg.get("message", {}).get("content", [])
            if not isinstance(content, list):
                content = []
            for c in content:
                if isinstance(c, dict) and c.get("type") == "tool_result":
                    lines.append(("dim", "[tool result]"))
    return lines[-OUTPUT_LINES:]


# ─── Widgets ──────────────────────────────────────────────────────────────────


def _status_display(data: AgentData) -> str:
    if data.agent_type == "main":
        status_colour, _ = STATUS_STYLE.get(data.status, ("dim", "?"))
        _, sym = STATUS_STYLE["main"]
    else:
        status_colour, sym = STATUS_STYLE.get(data.status, ("dim", "?"))
    desc = escape(data.description[:70])
    return f"[{status_colour}]{sym}[/{status_colour}]  [{status_colour}]{desc}[/{status_colour}]"


class AgentPane(Widget):
    DEFAULT_CSS = """
    AgentPane {
        height: auto;
        min-height: 18;
        border: solid $surface-lighten-1;
        padding: 1 2;
        margin: 0;
    }
    AgentPane.running     { border: solid $success; }
    AgentPane.interrupted { border: solid $warning; }
    AgentPane.completed   { border: solid $surface-lighten-1; opacity: 0.6; }
    AgentPane.unknown     { border: solid $surface-lighten-1; opacity: 0.6; }

    AgentPane .pane-title   { height: 1; text-style: bold; }
    AgentPane .pane-meta    { height: 1; color: $text-muted; }
    AgentPane .pane-divider { height: 1; color: $surface-lighten-2; }
    AgentPane .pane-output  {
        height: 10;
        overflow-y: auto;
        color: $text;
        padding-top: 1;
    }
    AgentPane.completed .pane-title { color: $text-muted; text-style: none; }
    AgentPane.unknown   .pane-title { color: $text-muted; text-style: none; }
    """

    def __init__(self, data: AgentData) -> None:
        super().__init__()
        self.data = data
        self.add_class(data.status)
        if data.agent_type == "main":
            self.add_class("pane--main")

    def compose(self) -> ComposeResult:
        yield Static(_status_display(self.data), classes="pane-title")
        project = Path(self.data.session.cwd).name
        yield Static(
            f"   [dim]{escape(self.data.agent_type[:40])}[/]  ·  [dim]{project}[/]",
            classes="pane-meta",
        )
        yield Static("   " + "─" * 60, classes="pane-divider")
        yield Static(self._output_markup(), classes="pane-output")

    def _output_markup(self) -> str:
        lines = _render_output(self.data.messages)
        if not lines:
            return "[dim]   no output yet[/dim]"
        parts = []
        for style, text in lines:
            safe = escape(text)
            parts.append(f"   [{style}]{safe}[/{style}]" if style else f"   {safe}")
        return "\n".join(parts)

    def refresh_data(self, data: AgentData) -> None:
        self.data = data
        self.remove_class("running", "completed", "interrupted", "unknown")
        self.add_class(data.status)
        if data.agent_type == "main":
            self.add_class("pane--main")
        else:
            self.remove_class("pane--main")
        self.query_one(".pane-title", Static).update(_status_display(data))
        project = Path(data.session.cwd).name
        self.query_one(".pane-meta", Static).update(
            f"   [dim]{escape(data.agent_type[:40])}[/]  ·  [dim]{project}[/]"
        )
        self.query_one(".pane-output", Static).update(self._output_markup())


class EmptyState(Widget):
    DEFAULT_CSS = """
    EmptyState {
        width: 1fr;
        height: 1fr;
        content-align: center middle;
        color: $text-muted;
    }
    """

    def __init__(self, project_filter: Path | None = None) -> None:
        super().__init__()
        self._project_filter = project_filter

    def compose(self) -> ComposeResult:
        if self._project_filter:
            msg = (
                f"[dim]No active Claude Code session in:\n\n"
                f"{escape(str(self._project_filter))}\n\n"
                "Start a Claude Code session in that directory\n"
                "and it will appear here.[/dim]"
            )
        else:
            msg = (
                "[dim]No active Claude Code sessions.\n\n"
                "Start a Claude Code session and it will appear here.[/dim]"
            )
        yield Static(msg, markup=True)


# ─── App ──────────────────────────────────────────────────────────────────────


class Dashboard(App):
    CSS = """
    Screen { background: $background; }

    #scroller {
        width: 1fr;
        height: 1fr;
        padding: 0 1;
    }

    #grid {
        grid-size: 2;
        grid-gutter: 1;
        height: auto;
    }

    #status-bar {
        height: 1;
        background: $surface;
        padding: 0 2;
        color: $text-muted;
        dock: bottom;
    }

    AgentPane.pane--main {
        border: tall $primary 40%;
    }
    """
    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("r", "refresh", "Refresh"),
    ]

    def __init__(self, project_filter: Path | None = None) -> None:
        super().__init__()
        self._project_filter = project_filter
        self.TITLE = (
            f"Claude Code Monitor — {project_filter.name}"
            if project_filter
            else "Claude Code Monitor"
        )

    def compose(self) -> ComposeResult:
        yield Header()
        yield ScrollableContainer(id="scroller")
        yield Static("", id="status-bar")
        yield Footer()

    def on_mount(self) -> None:
        self._pane_map: dict[str, AgentPane] = {}
        self._filter_label = (
            f"  ·  project: [dim]{escape(str(self._project_filter))}[/dim]"
            if self._project_filter
            else ""
        )
        self._do_refresh()
        self.set_interval(REFRESH_INTERVAL, self._do_refresh)

    def _do_refresh(self) -> None:
        agents = load_all_agents(self._project_filter)
        scroller = self.query_one("#scroller", ScrollableContainer)

        has_empty = bool(self.query("EmptyState"))
        has_grid = bool(self.query("#grid"))

        if not agents:
            if not has_empty:
                if has_grid:
                    self.query_one("#grid").remove()
                    self._pane_map.clear()
                scroller.mount(EmptyState(self._project_filter))
        else:
            if has_empty:
                self.query_one("EmptyState").remove()
                has_grid = False

            if not has_grid:
                grid = Grid(id="grid")
                scroller.mount(grid)

            grid = self.query_one("#grid", Grid)
            existing = set(self._pane_map)
            current = {a.key for a in agents}

            # Remove panes that are no longer in the agent list (expired or gone).
            for k in existing - current:
                self._pane_map.pop(k).remove()

            # Update or create panes, then enforce sorted order by moving each
            # pane to the correct position within the grid.
            for idx, a in enumerate(agents):
                if a.key in self._pane_map:
                    self._pane_map[a.key].refresh_data(a)
                else:
                    pane = AgentPane(a)
                    self._pane_map[a.key] = pane
                    grid.mount(pane)

            # Re-order children so they match the sorted agent list (newest first).
            for idx, a in enumerate(agents):
                grid.move_child(self._pane_map[a.key], before=idx)

        n_running = sum(1 for a in agents if a.status == "running")
        n_total = len(agents)
        ts = time.strftime("%H:%M:%S")
        self.query_one("#status-bar", Static).update(
            f"[green]{n_running} running[/green]  ·  [dim]{n_total} total[/dim]  ·  "
            f"auto-refresh {REFRESH_INTERVAL:g}s  ·  [dim]{ts}[/dim]{self._filter_label}"
        )

    def action_refresh(self) -> None:
        self._do_refresh()


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="cctop",
        description="Terminal dashboard for monitoring Claude Code subagents.",
    )
    parser.add_argument(
        "--project",
        metavar="DIR",
        default=None,
        help=(
            "Show only agents for the given project directory (default: current working directory)."
        ),
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Show agents from all projects instead of filtering by directory.",
    )
    args = parser.parse_args()

    if args.all and args.project is not None:
        parser.error("--all and --project are mutually exclusive")

    project_filter: Path | None = None
    if args.all:
        project_filter = None
    elif args.project is not None:
        project_filter = Path(args.project).resolve()
        if not project_filter.is_dir():
            parser.error(f"--project: directory does not exist: {project_filter}")
    else:
        project_filter = Path.cwd()

    Dashboard(project_filter=project_filter).run()


if __name__ == "__main__":
    main()
