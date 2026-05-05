# ruff: noqa: S101
"""Smoke tests verifying the Dashboard app starts and renders without error."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import ccmon
from ccmon import Dashboard


class TestDashboardStartup:
    async def test_app_starts_without_project_filter(self):
        async with Dashboard().run_test(headless=True) as pilot:
            assert pilot.app is not None

    async def test_app_starts_with_project_filter(self, tmp_path: Path):
        async with Dashboard(project_filter=tmp_path).run_test(headless=True) as pilot:
            assert pilot.app is not None

    async def test_app_title_default(self):
        async with Dashboard().run_test(headless=True) as pilot:
            title = pilot.app.TITLE or ""
            assert "Claude Code Monitor" in title

    async def test_app_title_with_project(self, tmp_path: Path):
        async with Dashboard(project_filter=tmp_path).run_test(headless=True) as pilot:
            title = pilot.app.TITLE or ""
            assert tmp_path.name in title

    async def test_quit_action(self):
        async with Dashboard().run_test(headless=True) as pilot:
            await pilot.press("q")


class TestMainArgParsing:
    """Tests for main() CLI argument parsing."""

    def _make_mock_dashboard(self):
        mock_instance = MagicMock()
        mock_instance.run.return_value = None
        mock_cls = MagicMock(return_value=mock_instance)
        return mock_cls, mock_instance

    def test_positional_dot(self, tmp_path: Path):
        """ccmon . → Dashboard called with project_filter=Path(".").resolve()"""
        mock_cls, mock_instance = self._make_mock_dashboard()
        with patch.object(ccmon, "Dashboard", mock_cls):
            with patch("sys.argv", ["ccmon", "."]):
                ccmon.main()
        mock_cls.assert_called_once_with(project_filter=Path(".").resolve())
        mock_instance.run.assert_called_once()

    def test_positional_tmp(self, tmp_path: Path):
        """ccmon /tmp → Dashboard called with project_filter=Path("/tmp")"""
        mock_cls, mock_instance = self._make_mock_dashboard()
        with patch.object(ccmon, "Dashboard", mock_cls):
            with patch("sys.argv", ["ccmon", str(tmp_path)]):
                ccmon.main()
        mock_cls.assert_called_once_with(project_filter=tmp_path.resolve())
        mock_instance.run.assert_called_once()

    def test_short_flag_p(self, tmp_path: Path):
        """ccmon -p /tmp → same as --project /tmp"""
        mock_cls, mock_instance = self._make_mock_dashboard()
        with patch.object(ccmon, "Dashboard", mock_cls):
            with patch("sys.argv", ["ccmon", "-p", str(tmp_path)]):
                ccmon.main()
        mock_cls.assert_called_once_with(project_filter=tmp_path.resolve())
        mock_instance.run.assert_called_once()

    def test_long_flag_project(self, tmp_path: Path):
        """ccmon --project /tmp → Dashboard called with project_filter=Path("/tmp")"""
        mock_cls, mock_instance = self._make_mock_dashboard()
        with patch.object(ccmon, "Dashboard", mock_cls):
            with patch("sys.argv", ["ccmon", "--project", str(tmp_path)]):
                ccmon.main()
        mock_cls.assert_called_once_with(project_filter=tmp_path.resolve())
        mock_instance.run.assert_called_once()

    def test_positional_and_project_mutually_exclusive(self, tmp_path: Path):
        """ccmon . --project /tmp → SystemExit (mutually exclusive)"""
        mock_cls, _ = self._make_mock_dashboard()
        with patch.object(ccmon, "Dashboard", mock_cls):
            with patch("sys.argv", ["ccmon", ".", "--project", str(tmp_path)]):
                with pytest.raises(SystemExit):
                    ccmon.main()

    def test_all_with_positional_mutually_exclusive(self, tmp_path: Path):
        """ccmon --all . → SystemExit (mutually exclusive)"""
        mock_cls, _ = self._make_mock_dashboard()
        with patch.object(ccmon, "Dashboard", mock_cls):
            with patch("sys.argv", ["ccmon", "--all", str(tmp_path)]):
                with pytest.raises(SystemExit):
                    ccmon.main()

    def test_no_args_uses_cwd(self):
        """ccmon (no args) → Dashboard called with project_filter=Path.cwd()"""
        mock_cls, mock_instance = self._make_mock_dashboard()
        with patch.object(ccmon, "Dashboard", mock_cls):
            with patch("sys.argv", ["ccmon"]):
                ccmon.main()
        mock_cls.assert_called_once_with(project_filter=Path.cwd())
        mock_instance.run.assert_called_once()
