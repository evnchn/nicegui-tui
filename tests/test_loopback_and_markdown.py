"""Selection-loopback bindings + markdown rendering."""
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
async def test_checkbox_loopback() -> None:
    def page() -> None:
        cb = ui.checkbox("accept")
        ui.label().bind_text_from(cb, "value",
                                  backward=lambda v: f"accepted = {bool(v)}")

    tc = TuiClient(page)
    tc.build()
    app = tc.build_app()
    async with app.run_test(size=(80, 20)) as pilot:
        await pilot.pause()
        from textual.widgets import Checkbox, Static
        cb = next(iter(app.query(Checkbox)))
        cb.focus()
        await pilot.pause()
        await pilot.press("space")  # toggle
        await pilot.pause()
        text = " ".join(str(s.render()) for s in app.query(Static))
        assert "accepted = True" in text, text
    tc.dispose()


@pytest.mark.asyncio
async def test_switch_loopback() -> None:
    def page() -> None:
        sw = ui.switch("enable")
        ui.label().bind_text_from(sw, "value",
                                  backward=lambda v: f"enabled = {bool(v)}")

    tc = TuiClient(page)
    tc.build()
    app = tc.build_app()
    async with app.run_test(size=(80, 20)) as pilot:
        await pilot.pause()
        from textual.widgets import Switch, Static
        sw = next(iter(app.query(Switch)))
        sw.focus()
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        text = " ".join(str(s.render()) for s in app.query(Static))
        assert "enabled = True" in text, text
    tc.dispose()


@pytest.mark.asyncio
async def test_markdown_is_parsed_not_shown_raw() -> None:
    def page() -> None:
        ui.markdown("**bold** and *italic* and `code`")

    tc = TuiClient(page)
    tc.build()
    app = tc.build_app()
    async with app.run_test(size=(100, 20)) as pilot:
        await pilot.pause()
        from textual.widgets import Markdown
        mds = list(app.query(Markdown))
        assert len(mds) == 1
        # Parsed markdown widgets instantiate MarkdownParagraph children;
        # raw Static would have none of those.
        child_types = [type(c).__name__ for c in mds[0].walk_children()]
        assert any("Markdown" in t for t in child_types), child_types
    tc.dispose()
