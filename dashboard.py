#!/usr/bin/env python3
"""Claude Agents Dashboard — monitor running Claude Code subagents."""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Grid, ScrollableContainer
from textual.widget import Widget
from textual.widgets import Footer, Header, Label, Static
from rich.markup import escape

# ─── Constants ────────────────────────────────────────────────────────────────

CLAUDE_DIR = Path.home() / ".claude"
SESSIONS_DIR = CLAUDE_DIR / "sessions"
PROJECTS_DIR = CLAUDE_DIR / "projects"
REFRESH_INTERVAL = 2.0

STATUS_STYLE: dict[str, tuple[str, str]] = {
    "running":     ("green",  "●"),
    "completed":   ("dim",    "○"),
    "interrupted": ("yellow", "◐"),
    "unknown":     ("dim",    "?"),
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


def _load_sessions() -> list[SessionInfo]:
    if not SESSIONS_DIR.exists():
        return []
    sessions = []
    for f in SESSIONS_DIR.glob("*.json"):
        try:
            data = json.loads(f.read_text())
            pid = data.get("pid")
            session_id = data.get("sessionId", "")
            cwd = data.get("cwd", "")
            if pid and session_id:
                sessions.append(SessionInfo(
                    pid=pid,
                    session_id=session_id,
                    cwd=cwd,
                    is_alive=_is_pid_alive(pid),
                ))
        except Exception:
            continue
    return sessions


def _infer_status(messages: list[dict], session_alive: bool) -> str:
    if not messages:
        return "unknown"
    last = messages[-1]
    if last.get("type") == "assistant":
        content = last.get("message", {}).get("content", [])
        # Agent is still waiting on a tool call
        if content and isinstance(content[-1], dict) and content[-1].get("type") == "tool_use":
            return "running" if session_alive else "interrupted"
        return "completed"
    if last.get("type") == "user":
        return "running" if session_alive else "interrupted"
    return "unknown"


def _load_messages(path: Path) -> list[dict]:
    try:
        return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
    except Exception:
        return []


def _load_agents_for_session(session: SessionInfo) -> list[AgentData]:
    project_dir = _cwd_to_project_dir(session.cwd)
    subagents_dir = PROJECTS_DIR / project_dir / session.session_id / "subagents"
    if not subagents_dir.exists():
        return []

    agents = []
    for meta_file in subagents_dir.glob("agent-*.meta.json"):
        try:
            meta = json.loads(meta_file.read_text())
            agent_id = meta_file.name.removeprefix("agent-").removesuffix(".meta.json")
            jsonl_path = meta_file.with_name(f"agent-{agent_id}.jsonl")
            messages = _load_messages(jsonl_path) if jsonl_path.exists() else []
            agent_type = meta.get("agentType", "unknown")
            agents.append(AgentData(
                agent_id=agent_id,
                description=meta.get("description") or agent_type,
                agent_type=agent_type,
                session=session,
                status=_infer_status(messages, session.is_alive),
                messages=messages,
            ))
        except Exception:
            continue
    return agents


def load_all_agents() -> list[AgentData]:
    agents: list[AgentData] = []
    for session in _load_sessions():
        agents.extend(_load_agents_for_session(session))
    agents.sort(key=lambda a: (a.status != "running", a.session.session_id, a.agent_id))
    return agents


# ─── Output rendering ─────────────────────────────────────────────────────────

def _render_output(messages: list[dict], n_lines: int = 10) -> list[tuple[str, str]]:
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
            for c in msg.get("message", {}).get("content", []) if isinstance(
                msg.get("message", {}).get("content"), list
            ) else []:
                if isinstance(c, dict) and c.get("type") == "tool_result":
                    lines.append(("dim", "[tool result]"))
    return lines[-n_lines:]


# ─── Widgets ──────────────────────────────────────────────────────────────────

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

    AgentPane .pane-title   { height: 1; text-style: bold; }
    AgentPane .pane-meta    { height: 1; color: $text-muted; }
    AgentPane .pane-divider { height: 1; color: $surface-lighten-2; }
    AgentPane .pane-output  {
        height: 10;
        overflow-y: auto;
        color: $text;
        padding-top: 1;
    }
    """

    def __init__(self, data: AgentData) -> None:
        super().__init__()
        self.data = data
        self.add_class(data.status)

    def compose(self) -> ComposeResult:
        color, dot = STATUS_STYLE.get(self.data.status, ("dim", "?"))
        yield Static(
            f"[{color}]{dot}[/{color}]  [{color}]{escape(self.data.description[:70])}[/{color}]",
            classes="pane-title",
        )
        project = Path(self.data.session.cwd).name
        yield Static(
            f"   [dim]{self.data.agent_type}[/]  ·  [dim]{project}[/]",
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
        color, dot = STATUS_STYLE.get(data.status, ("dim", "?"))
        self.query_one(".pane-title", Static).update(
            f"[{color}]{dot}[/{color}]  [{color}]{escape(data.description[:70])}[/{color}]"
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

    def compose(self) -> ComposeResult:
        yield Static(
            "[dim]No subagents found.\n\n"
            "Start a Claude Code session that spawns agents\n"
            "via the Agent tool and they'll appear here.[/dim]",
            markup=True,
        )


# ─── App ──────────────────────────────────────────────────────────────────────

class Dashboard(App):
    TITLE = "Claude Agents Dashboard"
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
    """
    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("r", "refresh", "Refresh"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        yield ScrollableContainer(id="scroller")
        yield Static("", id="status-bar")
        yield Footer()

    def on_mount(self) -> None:
        self._pane_map: dict[str, AgentPane] = {}
        self._do_refresh()
        self.set_interval(REFRESH_INTERVAL, self._do_refresh)

    def _do_refresh(self) -> None:
        agents = load_all_agents()
        scroller = self.query_one("#scroller", ScrollableContainer)

        has_empty = bool(self.query("EmptyState"))
        has_grid = bool(self.query("#grid"))

        if not agents:
            if not has_empty:
                if has_grid:
                    self.query_one("#grid").remove()
                    self._pane_map.clear()
                scroller.mount(EmptyState())
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

            for k in existing - current:
                self._pane_map.pop(k).remove()

            for a in agents:
                if a.key in self._pane_map:
                    self._pane_map[a.key].refresh_data(a)
                else:
                    pane = AgentPane(a)
                    self._pane_map[a.key] = pane
                    grid.mount(pane)

        running = sum(1 for a in agents if a.status == "running")
        ts = time.strftime("%H:%M:%S")
        self.query_one("#status-bar", Static).update(
            f"[green]{running} running[/green]  ·  {len(agents)} total  ·  "
            f"auto-refresh {int(REFRESH_INTERVAL)}s  ·  [dim]{ts}[/dim]"
        )

    def action_refresh(self) -> None:
        self._do_refresh()


def main() -> None:
    Dashboard().run()


if __name__ == "__main__":
    main()
