# ruff: noqa: S101
"""Unit tests for the data layer in dashboard.py."""

from __future__ import annotations

import json
import os
import time
from unittest.mock import patch

import dashboard
from dashboard import (
    AgentData,
    SessionInfo,
    _cwd_to_project_dir,
    _infer_status,
    _is_pid_alive,
    _load_sessions,
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
        with patch.object(dashboard, "SESSIONS_DIR", fake_sessions_dir):
            result = _load_sessions()
        assert result == []

    def test_returns_empty_list_when_dir_exists_but_empty(self, tmp_path):
        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir()
        with patch.object(dashboard, "SESSIONS_DIR", sessions_dir):
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
        with patch.object(dashboard, "SESSIONS_DIR", sessions_dir):
            result = _load_sessions()
        assert len(result) == 1
        assert result[0].session_id == "test-session-id"
        assert result[0].cwd == str(project_dir)

    def test_skips_invalid_json_files(self, tmp_path):
        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir()
        (sessions_dir / "bad.json").write_text("not valid json{{{")
        with patch.object(dashboard, "SESSIONS_DIR", sessions_dir):
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
        with patch.object(dashboard, "SESSIONS_DIR", sessions_dir):
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
        with patch.object(dashboard, "SESSIONS_DIR", sessions_dir):
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
        with patch.object(dashboard, "SESSIONS_DIR", sessions_dir):
            result = _load_sessions(project_filter=project_a.resolve())
        assert len(result) == 1
        assert result[0].session_id == "sess-a"


# ─── _infer_status ────────────────────────────────────────────────────────────

class TestInferStatus:
    def _tool_use_message(self, tool_name: str = "Bash") -> dict:
        return {
            "type": "assistant",
            "message": {
                "content": [
                    {"type": "tool_use", "name": tool_name, "input": {}}
                ]
            },
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
        from dashboard import _load_main_thread
        projects_dir = tmp_path / "projects"
        projects_dir.mkdir()
        session = SessionInfo(
            pid=os.getpid(), session_id="sess-abc", cwd=str(tmp_path / "myproject"), is_alive=True
        )
        with patch.object(dashboard, "PROJECTS_DIR", projects_dir):
            result = _load_main_thread(session)
        assert result is None

    def test_returns_agent_data_when_jsonl_exists(self, tmp_path):
        from dashboard import _load_main_thread
        projects_dir = tmp_path / "projects"
        projects_dir.mkdir()
        cwd = str(tmp_path / "myproject")
        project_dir = projects_dir / _cwd_to_project_dir(cwd)
        project_dir.mkdir(parents=True)
        session_id = "sess-xyz"
        msg = {"type": "assistant", "message": {"content": [{"type": "text", "text": "hello"}]}}
        (project_dir / f"{session_id}.jsonl").write_text(json.dumps(msg) + "\n")
        session = SessionInfo(pid=os.getpid(), session_id=session_id, cwd=cwd, is_alive=True)
        with patch.object(dashboard, "PROJECTS_DIR", projects_dir):
            result = _load_main_thread(session)
        assert result is not None
        assert result.agent_id == "__main__"
        assert result.agent_type == "main"

    def test_description_uses_cwd_basename(self, tmp_path):
        from dashboard import _load_main_thread
        projects_dir = tmp_path / "projects"
        projects_dir.mkdir()
        cwd = str(tmp_path / "my-cool-project")
        project_dir = projects_dir / _cwd_to_project_dir(cwd)
        project_dir.mkdir(parents=True)
        session_id = "sess-desc"
        (project_dir / f"{session_id}.jsonl").write_text("{}\n")
        session = SessionInfo(pid=os.getpid(), session_id=session_id, cwd=cwd, is_alive=True)
        with patch.object(dashboard, "PROJECTS_DIR", projects_dir):
            result = _load_main_thread(session)
        assert result is not None
        assert "my-cool-project" in result.description
