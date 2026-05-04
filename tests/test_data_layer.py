# ruff: noqa: S101
"""Unit tests for the data layer in cctop.py."""

from __future__ import annotations

import json
import os
import time
from unittest.mock import patch

import cctop
from cctop import (
    OUTPUT_LINES,
    AgentData,
    SessionInfo,
    _build_agent_type_lookup,
    _cwd_to_project_dir,
    _infer_status,
    _is_pid_alive,
    _last_skill_call,
    _load_sessions,
    _render_output,
)

# ─── _is_pid_alive ────────────────────────────────────────────────────────────


class TestIsPidAlive:
    def test_current_process_is_alive(self):
        assert _is_pid_alive(os.getpid()) is True

    def test_nonexistent_pid_is_dead(self):
        assert _is_pid_alive(99999999) is False


# ─── _cwd_to_project_dir ──────────────────────────────────────────────────────


class TestCwdToProjectDir:
    def test_slashes_become_dashes(self):
        assert _cwd_to_project_dir("/home/user/project") == "-home-user-project"

    def test_root_becomes_single_dash(self):
        assert _cwd_to_project_dir("/") == "-"

    def test_no_slashes_unchanged(self):
        assert _cwd_to_project_dir("nodots") == "nodots"

    def test_multiple_path_components(self):
        assert _cwd_to_project_dir("/a/b/c") == "-a-b-c"


# ─── AgentData.key ────────────────────────────────────────────────────────────


class TestAgentDataKey:
    def _make_session(self, session_id: str, cwd: str = "/home/user/project") -> SessionInfo:
        return SessionInfo(pid=1, session_id=session_id, cwd=cwd, is_alive=True)

    def test_key_format(self):
        session = self._make_session("sess-abc")
        agent = AgentData(
            agent_id="agent-123",
            description="test",
            agent_type="general-purpose",
            session=session,
            status="running",
        )
        assert agent.key == "sess-abc:agent-123"

    def test_key_is_session_colon_agent(self):
        session = self._make_session("mysession")
        agent = AgentData(
            agent_id="myagent",
            description="desc",
            agent_type="type",
            session=session,
            status="completed",
        )
        assert agent.key == "mysession:myagent"


# ─── _load_sessions ───────────────────────────────────────────────────────────


class TestLoadSessions:
    def test_returns_empty_list_when_sessions_dir_missing(self, tmp_path):
        fake_sessions_dir = tmp_path / "nonexistent_sessions"
        # fake_sessions_dir intentionally NOT created
        with patch.object(cctop, "SESSIONS_DIR", fake_sessions_dir):
            result = _load_sessions()
        assert result == []

    def test_returns_empty_list_when_dir_exists_but_empty(self, tmp_path):
        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir()
        with patch.object(cctop, "SESSIONS_DIR", sessions_dir):
            result = _load_sessions()
        assert result == []

    def test_loads_valid_session_file(self, tmp_path):
        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir()
        project_dir = tmp_path / "myproject"
        project_dir.mkdir()
        session_data = {
            "pid": os.getpid(),
            "sessionId": "test-session-id",
            "cwd": str(project_dir),
        }
        (sessions_dir / "test-session-id.json").write_text(json.dumps(session_data))
        with patch.object(cctop, "SESSIONS_DIR", sessions_dir):
            result = _load_sessions()
        assert len(result) == 1
        assert result[0].session_id == "test-session-id"
        assert result[0].cwd == str(project_dir)

    def test_skips_invalid_json_files(self, tmp_path):
        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir()
        (sessions_dir / "bad.json").write_text("not valid json{{{")
        with patch.object(cctop, "SESSIONS_DIR", sessions_dir):
            result = _load_sessions()
        assert result == []

    def test_skips_entries_missing_pid_or_session_id(self, tmp_path):
        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir()
        fake_cwd = str(tmp_path / "work")
        # missing sessionId
        (sessions_dir / "a.json").write_text(json.dumps({"pid": 1, "cwd": fake_cwd}))
        # missing pid
        (sessions_dir / "b.json").write_text(json.dumps({"sessionId": "x", "cwd": fake_cwd}))
        with patch.object(cctop, "SESSIONS_DIR", sessions_dir):
            result = _load_sessions()
        assert result == []

    def test_project_filter_excludes_mismatched_cwd(self, tmp_path):
        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir()
        project_a = tmp_path / "project_a"
        project_a.mkdir()
        session_data = {
            "pid": os.getpid(),
            "sessionId": "sess-a",
            "cwd": str(project_a),
        }
        (sessions_dir / "sess-a.json").write_text(json.dumps(session_data))
        different_project = tmp_path / "project_b"
        different_project.mkdir()
        with patch.object(cctop, "SESSIONS_DIR", sessions_dir):
            result = _load_sessions(project_filter=different_project)
        assert result == []

    def test_project_filter_includes_matching_cwd(self, tmp_path):
        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir()
        project_a = tmp_path / "project_a"
        project_a.mkdir()
        session_data = {
            "pid": os.getpid(),
            "sessionId": "sess-a",
            "cwd": str(project_a),
        }
        (sessions_dir / "sess-a.json").write_text(json.dumps(session_data))
        with patch.object(cctop, "SESSIONS_DIR", sessions_dir):
            result = _load_sessions(project_filter=project_a.resolve())
        assert len(result) == 1
        assert result[0].session_id == "sess-a"


# ─── _infer_status ────────────────────────────────────────────────────────────


class TestInferStatus:
    def _tool_use_message(self, tool_name: str = "Bash") -> dict:
        return {
            "type": "assistant",
            "message": {"content": [{"type": "tool_use", "name": tool_name, "input": {}}]},
        }

    def _text_message(self) -> dict:
        return {
            "type": "assistant",
            "message": {"content": [{"type": "text", "text": "done"}]},
        }

    def _user_message(self) -> dict:
        return {"type": "user", "message": {"content": [{"type": "tool_result"}]}}

    def test_empty_messages_returns_unknown(self):
        assert _infer_status([], session_alive=True) == "unknown"

    def test_completed_when_last_message_is_text(self):
        messages = [self._text_message()]
        assert _infer_status(messages, session_alive=True, jsonl_mtime=time.time()) == "completed"

    def test_running_when_last_is_tool_use_and_session_alive_and_fresh(self):
        messages = [self._tool_use_message()]
        mtime = time.time()  # fresh
        assert _infer_status(messages, session_alive=True, jsonl_mtime=mtime) == "running"

    def test_interrupted_when_last_is_tool_use_and_session_dead(self):
        messages = [self._tool_use_message()]
        mtime = time.time()
        assert _infer_status(messages, session_alive=False, jsonl_mtime=mtime) == "interrupted"

    def test_interrupted_when_last_is_tool_use_and_stale(self):
        messages = [self._tool_use_message()]
        old_mtime = time.time() - 100  # older than STALE_THRESHOLD_SECONDS (5)
        assert _infer_status(messages, session_alive=True, jsonl_mtime=old_mtime) == "interrupted"

    def test_running_when_last_is_user_message_and_alive_and_fresh(self):
        messages = [self._user_message()]
        mtime = time.time()
        assert _infer_status(messages, session_alive=True, jsonl_mtime=mtime) == "running"

    def test_interrupted_when_last_is_user_message_and_dead(self):
        messages = [self._user_message()]
        mtime = time.time()
        assert _infer_status(messages, session_alive=False, jsonl_mtime=mtime) == "interrupted"

    def test_unknown_for_unrecognised_message_type(self):
        messages = [{"type": "system", "message": {}}]
        assert _infer_status(messages, session_alive=True) == "unknown"


# ─── SessionInfo ──────────────────────────────────────────────────────────────


class TestSessionInfo:
    def test_instantiation(self, tmp_path):
        s = SessionInfo(pid=42, session_id="abc", cwd=str(tmp_path), is_alive=True)
        assert s.pid == 42
        assert s.session_id == "abc"
        assert s.cwd == str(tmp_path)
        assert s.is_alive is True

    def test_dead_session(self, tmp_path):
        s = SessionInfo(pid=99, session_id="dead", cwd=str(tmp_path), is_alive=False)
        assert s.is_alive is False


# ─── _load_main_thread ────────────────────────────────────────────────────────


class TestLoadMainThread:
    def test_returns_none_when_jsonl_missing(self, tmp_path):
        from cctop import _load_main_thread

        projects_dir = tmp_path / "projects"
        projects_dir.mkdir()
        session = SessionInfo(
            pid=os.getpid(), session_id="sess-abc", cwd=str(tmp_path / "myproject"), is_alive=True
        )
        with patch.object(cctop, "PROJECTS_DIR", projects_dir):
            result = _load_main_thread(session)
        assert result is None

    def test_returns_agent_data_when_jsonl_exists(self, tmp_path):
        from cctop import _load_main_thread

        projects_dir = tmp_path / "projects"
        projects_dir.mkdir()
        cwd = str(tmp_path / "myproject")
        project_dir = projects_dir / _cwd_to_project_dir(cwd)
        project_dir.mkdir(parents=True)
        session_id = "sess-xyz"
        msg = {"type": "assistant", "message": {"content": [{"type": "text", "text": "hello"}]}}
        (project_dir / f"{session_id}.jsonl").write_text(json.dumps(msg) + "\n")
        session = SessionInfo(pid=os.getpid(), session_id=session_id, cwd=cwd, is_alive=True)
        with patch.object(cctop, "PROJECTS_DIR", projects_dir):
            result = _load_main_thread(session)
        assert result is not None
        assert result.agent_id == "__main__"
        assert result.agent_type == "main"

    def test_description_uses_cwd_basename(self, tmp_path):
        from cctop import _load_main_thread

        projects_dir = tmp_path / "projects"
        projects_dir.mkdir()
        cwd = str(tmp_path / "my-cool-project")
        project_dir = projects_dir / _cwd_to_project_dir(cwd)
        project_dir.mkdir(parents=True)
        session_id = "sess-desc"
        (project_dir / f"{session_id}.jsonl").write_text("{}\n")
        session = SessionInfo(pid=os.getpid(), session_id=session_id, cwd=cwd, is_alive=True)
        with patch.object(cctop, "PROJECTS_DIR", projects_dir):
            result = _load_main_thread(session)
        assert result is not None
        assert "my-cool-project" in result.description


# ─── _render_output ───────────────────────────────────────────────────────────


class TestRenderOutput:
    def _text_msg(self, text: str) -> dict:
        return {"type": "assistant", "message": {"content": [{"type": "text", "text": text}]}}

    def _tool_msg(self, name: str, cmd: str = "") -> dict:
        inp = {"command": cmd} if name == "Bash" else {}
        return {
            "type": "assistant",
            "message": {"content": [{"type": "tool_use", "name": name, "input": inp}]},
        }

    def _user_result_msg(self) -> dict:
        return {"type": "user", "message": {"content": [{"type": "tool_result"}]}}

    def test_empty_messages_returns_empty_list(self):
        assert _render_output([]) == []

    def test_assistant_text_message(self):
        assert _render_output([self._text_msg("hello")]) == [("", "hello")]

    def test_blank_lines_in_text_skipped(self):
        result = _render_output([self._text_msg("line1\n\nline2")])
        assert result == [("", "line1"), ("", "line2")]

    def test_text_truncated_to_140_chars(self):
        result = _render_output([self._text_msg("x" * 200)])
        assert result == [("", "x" * 140)]

    def test_bash_tool_use(self):
        assert _render_output([self._tool_msg("Bash", "echo hello")]) == [("dim", "$ echo hello")]

    def test_non_bash_tool_use(self):
        assert _render_output([self._tool_msg("Read")]) == [("dim", "→ Read")]

    def test_user_tool_result(self):
        assert _render_output([self._user_result_msg()]) == [("dim", "[tool result]")]

    def test_returns_last_output_lines_only(self):
        msgs = [self._text_msg(f"line {i}") for i in range(OUTPUT_LINES + 5)]
        result = _render_output(msgs)
        assert len(result) == OUTPUT_LINES
        assert result[-1] == ("", f"line {OUTPUT_LINES + 4}")


# ─── _build_agent_type_lookup ─────────────────────────────────────────────────


class TestBuildAgentTypeLookup:
    def _agent_line(self, description: str, subagent_type: str) -> str:
        import json

        entry = {
            "type": "assistant",
            "message": {
                "content": [
                    {
                        "type": "tool_use",
                        "name": "Agent",
                        "input": {"description": description, "subagent_type": subagent_type},
                    }
                ]
            },
        }
        return json.dumps(entry)

    def test_missing_jsonl_returns_empty_dict(self, tmp_path):
        projects_dir = tmp_path / "projects"
        projects_dir.mkdir()
        with patch.object(cctop, "PROJECTS_DIR", projects_dir):
            result = _build_agent_type_lookup("sess-x", "-home-user-proj")
        assert result == {}

    def test_valid_agent_tool_call_captured(self, tmp_path):
        projects_dir = tmp_path / "projects"
        project_dir = projects_dir / "-home-user-proj"
        project_dir.mkdir(parents=True)
        (project_dir / "sess-x.jsonl").write_text(
            self._agent_line("my task", "general-purpose") + "\n"
        )
        with patch.object(cctop, "PROJECTS_DIR", projects_dir):
            result = _build_agent_type_lookup("sess-x", "-home-user-proj")
        assert result == {"my task": "general-purpose"}

    def test_invalid_json_line_skipped(self, tmp_path):
        projects_dir = tmp_path / "projects"
        project_dir = projects_dir / "-home-user-proj"
        project_dir.mkdir(parents=True)
        (project_dir / "sess-x.jsonl").write_text("not valid json{{{\n")
        with patch.object(cctop, "PROJECTS_DIR", projects_dir):
            result = _build_agent_type_lookup("sess-x", "-home-user-proj")
        assert result == {}

    def test_multiple_agent_calls_all_captured(self, tmp_path):
        projects_dir = tmp_path / "projects"
        project_dir = projects_dir / "-home-user-proj"
        project_dir.mkdir(parents=True)
        lines = (
            "\n".join(
                [
                    self._agent_line("task one", "general-purpose"),
                    self._agent_line("task two", "code-reviewer"),
                ]
            )
            + "\n"
        )
        (project_dir / "sess-x.jsonl").write_text(lines)
        with patch.object(cctop, "PROJECTS_DIR", projects_dir):
            result = _build_agent_type_lookup("sess-x", "-home-user-proj")
        assert result == {"task one": "general-purpose", "task two": "code-reviewer"}


# ─── _last_skill_call ─────────────────────────────────────────────────────────


class TestLastSkillCall:
    def _skill_msg(self, skill_name: str) -> dict:
        return {
            "type": "assistant",
            "message": {
                "content": [{"type": "tool_use", "name": "Skill", "input": {"skill": skill_name}}]
            },
        }

    def test_empty_messages_returns_none(self):
        assert _last_skill_call([]) is None

    def test_no_skill_calls_returns_none(self):
        msg = {"type": "assistant", "message": {"content": [{"type": "text", "text": "hi"}]}}
        assert _last_skill_call([msg]) is None

    def test_single_skill_call_returns_name(self):
        assert _last_skill_call([self._skill_msg("my-skill")]) == "my-skill"

    def test_multiple_skill_calls_returns_last(self):
        msgs = [self._skill_msg("first"), self._skill_msg("second")]
        assert _last_skill_call(msgs) == "second"

    def test_string_content_is_skipped(self):
        """Message whose content is a plain string (not a list) hits the continue branch."""
        msg = {"type": "assistant", "message": {"content": "plain string, not a list"}}
        assert _last_skill_call([msg]) is None


# ─── _load_messages ───────────────────────────────────────────────────────────


class TestLoadMessages:
    def test_invalid_jsonl_returns_empty_list(self, tmp_path):
        from cctop import _load_messages

        bad_file = tmp_path / "bad.jsonl"
        bad_file.write_text("not json{")
        result = _load_messages(bad_file)
        assert result == []

    def test_valid_jsonl_returns_parsed_lines(self, tmp_path):
        from cctop import _load_messages

        good_file = tmp_path / "good.jsonl"
        msg = {"type": "assistant", "message": {"content": []}}
        good_file.write_text(json.dumps(msg) + "\n")
        result = _load_messages(good_file)
        assert result == [msg]

    def test_blank_lines_are_skipped(self, tmp_path):
        from cctop import _load_messages

        f = tmp_path / "msgs.jsonl"
        msg = {"type": "user"}
        f.write_text("\n" + json.dumps(msg) + "\n\n")
        result = _load_messages(f)
        assert result == [msg]


# ─── _build_agent_type_lookup (non-list content) ──────────────────────────────


class TestBuildAgentTypeLookupEdgeCases:
    def test_string_content_is_skipped(self, tmp_path):
        """Lines where message.content is a plain string hit the `continue` branch."""
        projects_dir = tmp_path / "projects"
        project_dir = projects_dir / "-home-user-proj"
        project_dir.mkdir(parents=True)
        entry = {"type": "assistant", "message": {"content": "plain string"}}
        (project_dir / "sess-x.jsonl").write_text(json.dumps(entry) + "\n")
        with patch.object(cctop, "PROJECTS_DIR", projects_dir):
            result = _build_agent_type_lookup("sess-x", "-home-user-proj")
        assert result == {}


# ─── _load_agents_for_session ─────────────────────────────────────────────────


class TestLoadAgentsForSession:
    def _make_session(
        self, cwd: str, session_id: str = "sess-abc", pid: int | None = None
    ) -> SessionInfo:
        return SessionInfo(
            pid=pid if pid is not None else os.getpid(),
            session_id=session_id,
            cwd=cwd,
            is_alive=True,
        )

    def _write_meta(
        self,
        subagents_dir,
        agent_id: str,
        description: str = "task",
        agent_type: str = "general-purpose",
    ) -> None:
        meta = {"description": description, "agentType": agent_type}
        (subagents_dir / f"agent-{agent_id}.meta.json").write_text(json.dumps(meta))

    def test_missing_jsonl_loads_agent_with_empty_messages(self, tmp_path):
        """An agent with a .meta.json but no .jsonl still loads with empty messages."""
        from cctop import _load_agents_for_session

        cwd = str(tmp_path / "myproject")
        session = self._make_session(cwd)
        project_dir_name = _cwd_to_project_dir(cwd)
        subagents_dir = tmp_path / "projects" / project_dir_name / session.session_id / "subagents"
        subagents_dir.mkdir(parents=True)
        self._write_meta(subagents_dir, "001", description="my task")

        with patch.object(cctop, "PROJECTS_DIR", tmp_path / "projects"):
            agents = _load_agents_for_session(session)

        assert len(agents) == 1
        assert agents[0].messages == []
        assert agents[0].agent_id == "001"

    def test_manager_agent_with_skill_call_shows_skill_name(self, tmp_path):
        """Agent with agent_type 'manager' and a Skill tool call shows 'manager → <skill>'."""
        from cctop import _load_agents_for_session

        cwd = str(tmp_path / "myproject")
        session = self._make_session(cwd)
        project_dir_name = _cwd_to_project_dir(cwd)
        projects_dir = tmp_path / "projects"
        subagents_dir = projects_dir / project_dir_name / session.session_id / "subagents"
        subagents_dir.mkdir(parents=True)

        agent_id = "mgr-001"
        # Write .meta.json with agentType=manager
        meta = {"description": "manager task", "agentType": "manager"}
        (subagents_dir / f"agent-{agent_id}.meta.json").write_text(json.dumps(meta))

        # Write .jsonl with a Skill tool-use call
        skill_msg = {
            "type": "assistant",
            "message": {
                "content": [
                    {"type": "tool_use", "name": "Skill", "input": {"skill": "code-review"}}
                ]
            },
        }
        (subagents_dir / f"agent-{agent_id}.jsonl").write_text(json.dumps(skill_msg) + "\n")

        with patch.object(cctop, "PROJECTS_DIR", projects_dir):
            agents = _load_agents_for_session(session)

        assert len(agents) == 1
        assert agents[0].agent_type == "manager → code-review"

    def test_bad_meta_json_is_skipped(self, tmp_path):
        """A .meta.json with invalid JSON is caught and that agent is not returned."""
        from cctop import _load_agents_for_session

        cwd = str(tmp_path / "myproject")
        session = self._make_session(cwd)
        project_dir_name = _cwd_to_project_dir(cwd)
        subagents_dir = tmp_path / "projects" / project_dir_name / session.session_id / "subagents"
        subagents_dir.mkdir(parents=True)
        (subagents_dir / "agent-bad.meta.json").write_text("INVALID JSON{")

        with patch.object(cctop, "PROJECTS_DIR", tmp_path / "projects"):
            agents = _load_agents_for_session(session)

        assert agents == []


# ─── load_all_agents ──────────────────────────────────────────────────────────


class TestLoadAllAgents:
    def _write_session(self, sessions_dir, session_id: str, cwd: str, pid: int) -> None:
        data = {"pid": pid, "sessionId": session_id, "cwd": cwd}
        (sessions_dir / f"{session_id}.json").write_text(json.dumps(data))

    def test_dead_session_is_skipped(self, tmp_path):
        """A session whose pid is not alive is excluded entirely by load_all_agents."""
        from cctop import load_all_agents

        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir()
        projects_dir = tmp_path / "projects"
        projects_dir.mkdir()
        cwd = str(tmp_path / "myproject")
        self._write_session(sessions_dir, "sess-dead", cwd, pid=999999)

        with patch.object(cctop, "SESSIONS_DIR", sessions_dir), \
             patch.object(cctop, "PROJECTS_DIR", projects_dir):
            agents = load_all_agents()

        assert agents == []

    def test_stale_non_running_agent_with_recent_mtime_is_included(self, tmp_path):
        """Non-running agent with recent mtime is included (within EXPIRE_SECONDS)."""
        from cctop import load_all_agents

        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir()
        projects_dir = tmp_path / "projects"
        cwd = str(tmp_path / "myproject")
        session_id = "sess-stale"
        self._write_session(sessions_dir, session_id, cwd, pid=os.getpid())

        # Set up main thread JSONL with a completed (text) message
        project_dir_name = _cwd_to_project_dir(cwd)
        project_dir = projects_dir / project_dir_name
        project_dir.mkdir(parents=True)
        msg = {"type": "assistant", "message": {"content": [{"type": "text", "text": "done"}]}}
        jsonl_path = project_dir / f"{session_id}.jsonl"
        jsonl_path.write_text(json.dumps(msg) + "\n")

        with patch.object(cctop, "SESSIONS_DIR", sessions_dir), \
             patch.object(cctop, "PROJECTS_DIR", projects_dir):
            agents = load_all_agents()

        # The main thread agent should appear because mtime is very recent (just written)
        assert any(a.agent_id == "__main__" for a in agents)


# ─── _render_output (non-dict content items) ─────────────────────────────────


class TestRenderOutputEdgeCases:
    def test_non_dict_content_item_is_skipped(self):
        """An assistant message whose content list contains a plain string is skipped gracefully."""
        msg = {
            "type": "assistant",
            "message": {"content": ["plain string item", {"type": "text", "text": "hello"}]},
        }
        result = _render_output([msg])
        assert result == [("", "hello")]

    def test_user_message_with_string_content_is_handled(self):
        """A user message where content is a plain string (not list) produces no lines."""
        msg = {"type": "user", "message": {"content": "not a list"}}
        result = _render_output([msg])
        assert result == []
