"""ui.sub_pages: default route renders, navigate_sub_pages swaps content."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from nicegui import ui  # noqa: E402
from nicegui_tui.client import TuiClient, install_hooks  # noqa: E402


@pytest.fixture(autouse=True)
def _hooks():
    install_hooks()


@pytest.mark.asyncio
async def test_sub_pages_renders_default_route() -> None:
    def home():
        ui.label("HOME_BODY")

    def about():
        ui.label("ABOUT_BODY")

    def page():
        ui.label("layout-header")
        ui.sub_pages({"/": home, "/about": about})

    tc = TuiClient(page)
    tc.build()
    app = tc.build_app()
    async with app.run_test(size=(80, 20)) as pilot:
        await pilot.pause()
        from textual.widgets import Static
        text = " ".join(str(s.render()) for s in app.query(Static))
        assert "HOME_BODY" in text, text
        assert "ABOUT_BODY" not in text, text
    tc.dispose()


@pytest.mark.asyncio
async def test_sub_pages_navigate_swaps_content() -> None:
    def home():
        ui.label("HOME_BODY")

    def about():
        ui.label("ABOUT_BODY")

    def page():
        ui.sub_pages({"/": home, "/about": about})

    tc = TuiClient(page)
    tc.build()
    app = tc.build_app()
    async with app.run_test(size=(80, 20)) as pilot:
        await pilot.pause()
        routes = tc.collect_sub_page_routes()
        assert ("/" in [p for _, p in routes]
                and "/about" in [p for _, p in routes])
        sp_id = routes[0][0]
        tc.navigate_sub_pages(sp_id, "/about")
        await pilot.pause()
        from textual.widgets import Static
        text = " ".join(str(s.render()) for s in app.query(Static))
        assert "ABOUT_BODY" in text, text
        assert "HOME_BODY" not in text, text
    tc.dispose()
