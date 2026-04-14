"""Verify NiceGUI binding propagates to TUI widgets (homepage text-reversal example)."""
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
async def test_bind_text_from_input_propagates_to_label() -> None:
    def page() -> None:
        inp = ui.input("text")
        lbl = ui.label("start")
        lbl.bind_text_from(inp, "value", backward=lambda v: (v or "")[::-1])

    tc = TuiClient(page)
    tc.build()
    app = tc.build_app()
    async with app.run_test(size=(100, 20)) as pilot:
        await pilot.pause()
        from textual.widgets import Input, Static
        ipt = next(iter(app.query(Input)))
        ipt.focus()
        await pilot.press("h", "e", "l", "l", "o")
        await pilot.pause()
        rendered = [str(s.render()) for s in app.query(Static)
                    if "unsupported" not in str(s.render())]
        assert any("olleh" in t for t in rendered), rendered
    tc.dispose()
