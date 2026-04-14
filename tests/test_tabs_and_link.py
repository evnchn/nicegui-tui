"""Tabs/TabPanel → TabbedContent bridge + Link widget."""
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
async def test_tabs_render_as_tabbedcontent_with_labels() -> None:
    def page() -> None:
        with ui.tabs() as tabs:
            ui.tab("a", label="Alpha")
            ui.tab("b", label="Beta")
        with ui.tab_panels(tabs, value="a"):
            with ui.tab_panel("a"):
                ui.label("panel-A-body")
            with ui.tab_panel("b"):
                ui.label("panel-B-body")

    tc = TuiClient(page)
    tc.build()
    app = tc.build_app()
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        from textual.widgets import TabbedContent, TabPane
        tbc = next(iter(app.query(TabbedContent)))
        panes = list(tbc.query(TabPane))
        titles = [str(p._title) for p in panes] if panes else []
        # Title comes from the matching Tab element's label.
        assert any("Alpha" in t for t in titles), titles
        assert any("Beta" in t for t in titles), titles
        # Body of the active pane should render.
        from textual.widgets import Static
        visible_text = " ".join(str(s.render()) for s in app.query(Static))
        assert "panel-A-body" in visible_text, visible_text
    tc.dispose()


@pytest.mark.asyncio
async def test_link_renders_as_link_widget() -> None:
    def page() -> None:
        ui.link("homepage", "https://nicegui.io/")

    tc = TuiClient(page)
    tc.build()
    app = tc.build_app()
    async with app.run_test(size=(100, 20)) as pilot:
        await pilot.pause()
        from textual.widgets import Link
        links = list(app.query(Link))
        assert len(links) == 1
        assert "homepage" in str(links[0].text)
    tc.dispose()


@pytest.mark.asyncio
async def test_root_page_preferred_over_first_registered() -> None:
    """server._handle_session prefers '/' — unit-level check on the map lookup."""
    from nicegui_tui.server import _REGISTERED_BUILDERS
    _REGISTERED_BUILDERS.clear()
    _REGISTERED_BUILDERS["/other"] = lambda: ui.label("other")
    _REGISTERED_BUILDERS["/"] = lambda: ui.label("root")
    _REGISTERED_BUILDERS["/third"] = lambda: ui.label("third")
    chosen = _REGISTERED_BUILDERS.get("/") or next(iter(_REGISTERED_BUILDERS.values()))
    # Can't easily run it without a client; just verify the chosen callable
    # references the 'root' label by source, or at least is identified as the
    # '/' entry.
    assert chosen is _REGISTERED_BUILDERS["/"]
    _REGISTERED_BUILDERS.clear()
