"""Regression tests for dialog open/close via ModalScreen and Row child visibility."""
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
async def test_row_renders_all_children_at_reasonable_width() -> None:
    def page() -> None:
        with ui.row():
            ui.button("Increment")
            ui.label("count: 0")
            ui.button("Warn")
            ui.button("Error")

    tc = TuiClient(page)
    tc.build()
    app = tc.build_app()
    async with app.run_test(size=(120, 30)) as pilot:
        await pilot.pause()
        rows = list(app.query("NGRow"))
        assert rows, "no NGRow mounted"
        row = rows[0]
        visible_children = [c for c in row.children if c.display and c.region.x < 120]
        labels = []
        from textual.widgets import Button, Static
        for c in row.children:
            if isinstance(c, Button):
                labels.append(str(c.label))
            elif isinstance(c, Static):
                labels.append(str(c.render()))
        assert "Increment" in labels
        assert "Warn" in labels
        assert "Error" in labels
        in_viewport = [c for c in row.children if 0 <= c.region.x < 120 and c.region.right <= 120]
        in_viewport_labels = []
        for c in in_viewport:
            if isinstance(c, Button):
                in_viewport_labels.append(str(c.label))
            elif isinstance(c, Static):
                in_viewport_labels.append(str(c.render()))
        assert "Warn" in in_viewport_labels, (
            f"Warn button clipped off-screen; viewport kids: {in_viewport_labels}")
        assert "Error" in in_viewport_labels, (
            f"Error button clipped off-screen; viewport kids: {in_viewport_labels}")
    tc.dispose()


@pytest.mark.asyncio
async def test_dialog_opens_and_closes_via_button() -> None:
    def page() -> None:
        with ui.dialog() as dlg, ui.card():
            ui.label("dialog body text").mark("dialog-body")
            ui.button("Close", on_click=dlg.close).mark("close-btn")
        ui.button("Open dialog", on_click=dlg.open).mark("open-btn")

    tc = TuiClient(page)
    tc.build()
    app = tc.build_app()
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        from textual.widgets import Button, Static
        open_btn = next(b for b in app.query(Button) if str(b.label) == "Open dialog")
        open_btn.press()
        await pilot.pause()
        # After open, the screen stack should have one more entry.
        assert len(app.screen_stack) >= 2, f"expected modal pushed, stack={app.screen_stack}"
        top = app.screen
        texts = [str(s.render()) for s in top.query(Static)]
        assert any("dialog body text" in t for t in texts), texts

        close_btn = next(b for b in top.query(Button) if str(b.label) == "Close")
        close_btn.press()
        await pilot.pause()
        assert len(app.screen_stack) == 1, (
            f"expected modal popped, stack={app.screen_stack}")
    tc.dispose()
