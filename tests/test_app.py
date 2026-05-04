# ruff: noqa: S101
"""Smoke tests verifying the Dashboard app starts and renders without error."""

from __future__ import annotations

from pathlib import Path

from cctop import Dashboard


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
