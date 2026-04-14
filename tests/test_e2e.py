"""End-to-end tests for nicegui-tui.

We run two complementary flavours of E2E:

1. **In-process bridge test** — uses Textual's ``App.run_test()`` to drive a
   ``TuiClient`` that shares state with a NiceGUI client built from the same
   page builder. This proves the element-tree bridge, event dispatch, shared
   state, ``tui-hide`` / ``tui-only`` opt-outs, and unsupported-element
   warnings, without SSH transport complexity.

2. **SSH connection smoke test** — starts the actual asyncssh server, opens
   an SSH connection with a PTY using asyncssh's client, reads back at least
   the alt-screen enter sequence as proof the Textual app started.

Both must pass for the package to be considered "E2E green".
"""
from __future__ import annotations

import asyncio
import logging
import socket
import sys
from pathlib import Path

import asyncssh
import pytest
import pytest_asyncio

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from nicegui import ui  # noqa: E402
from nicegui_tui.checker import get_logger, reset_warnings  # noqa: E402
from nicegui_tui.client import TuiClient, install_hooks  # noqa: E402
from nicegui_tui.server import _start_server, _REGISTERED_BUILDERS  # noqa: E402


# Shared app state used across the two page builder factories. The E2E test
# asserts that pressing a button in the TUI updates this state and is visible
# to a *second* independent TUI session.
APP_STATE: dict[str, int | str | bool] = {"count": 0, "last_input": ""}


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def make_page_builder():
    """Return a fresh page-builder function referencing :data:`APP_STATE`."""
    def page() -> None:
        ui.label("Gallery").classes("tcss-primary")
        ui.markdown("**markdown** content").classes("tcss-muted")

        def bump() -> None:
            APP_STATE["count"] = int(APP_STATE["count"]) + 1  # type: ignore[arg-type]
            counter.set_text(f"count: {APP_STATE['count']}")

        btn = ui.button("bump", on_click=bump)
        btn.mark("bump-btn")
        counter = ui.label(f"count: {APP_STATE['count']}")
        counter.mark("counter")

        ui.input("name", on_change=lambda e: APP_STATE.update(last_input=e.value))
        ui.textarea("notes")
        ui.checkbox("accept")
        ui.switch()
        ui.radio(["x", "y", "z"], value="x")
        ui.select(["1", "2", "3"], value="1")
        ui.separator()
        with ui.row(): ui.label("r1"); ui.label("r2")
        with ui.column(): ui.label("c1")
        with ui.card(): ui.label("card-body")

        with ui.dialog() as d, ui.card():
            ui.label("dialog body")
        ui.button("open", on_click=d.open)

        ui.label("tui-only marker").classes("tui-only")
        ui.label("browser-only marker").classes("tui-hide")

        # Unsupported: must log a warning.
        try:
            ui.aggrid({"columnDefs": [{"field": "x"}], "rowData": [{"x": 1}]})
        except Exception:
            pass

    return page


@pytest_asyncio.fixture(autouse=True)
async def _setup():
    install_hooks()
    reset_warnings()
    APP_STATE.update(count=0, last_input="")
    yield


# ---------------------------------------------------------------------------
# 1. In-process bridge E2E
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_in_process_bridge(caplog) -> None:
    caplog.set_level(logging.WARNING, logger="nicegui_tui")
    builder = make_page_builder()

    tc = TuiClient(builder)
    tc.build()
    app = tc.build_app()

    async with app.run_test(size=(100, 40)) as pilot:
        await pilot.pause()

        # (a) click a button -> shared state updates
        from textual.widgets import Button, Static
        buttons = list(app.query(Button))
        bump_btn = next(b for b in buttons if str(b.label) == "bump")
        bump_btn.press()
        await pilot.pause()
        assert APP_STATE["count"] == 1, APP_STATE

        # counter label should have updated via the monkey-patched update hook
        labels_text = [str(s.render()) for s in app.query(Static)]
        assert any("count: 1" in t for t in labels_text), labels_text

        # (c) unsupported element logged as WARN
        assert any("AgGrid" in r.getMessage() or "not supported" in r.getMessage()
                   for r in caplog.records), [r.getMessage() for r in caplog.records]

        # (d) tui-hide skipped; tui-only rendered in TUI
        assert not any("browser-only marker" in t for t in labels_text), labels_text
        assert any("tui-only marker" in t for t in labels_text), labels_text

    tc.dispose()


# ---------------------------------------------------------------------------
# 1b. Second independent session sees shared state
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_second_session_sees_state() -> None:
    builder = make_page_builder()

    # First session bumps count to 3.
    tc1 = TuiClient(builder)
    tc1.build()
    app1 = tc1.build_app()
    async with app1.run_test(size=(80, 30)) as pilot:
        await pilot.pause()
        from textual.widgets import Button
        bump_btn = next(b for b in app1.query(Button) if str(b.label) == "bump")
        for _ in range(3):
            bump_btn.press()
            await pilot.pause()
    tc1.dispose()

    assert APP_STATE["count"] == 3

    # Second session: a fresh page builder reads APP_STATE on mount.
    tc2 = TuiClient(builder)
    tc2.build()
    app2 = tc2.build_app()
    async with app2.run_test(size=(80, 30)) as pilot:
        await pilot.pause()
        from textual.widgets import Static
        labels_text = [str(s.render()) for s in app2.query(Static)]
        assert any("count: 3" in t for t in labels_text), labels_text
    tc2.dispose()


# ---------------------------------------------------------------------------
# 2. SSH server smoke test
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ssh_server_accepts_connection_and_launches_tui() -> None:
    """Start the real SSH server, connect via asyncssh, verify the Textual app
    runs (we look for the alt-screen enter escape sequence on stdout).
    """
    port = _free_port()
    builder = make_page_builder()

    _REGISTERED_BUILDERS.clear()
    _REGISTERED_BUILDERS["/"] = builder

    acceptor = await _start_server(port=port, host="127.0.0.1", host_key_path=None)
    try:
        async with asyncssh.connect(
            "127.0.0.1",
            port=port,
            username="tui",
            known_hosts=None,
            client_keys=None,
            password=None,
        ) as conn:
            # Open a PTY-backed session. asyncssh returns (stdin, stdout, stderr).
            stdin, stdout, _stderr = await conn.open_session(
                command=None, term_type="xterm-256color", term_size=(100, 30),
                encoding="utf-8",
            )
            reader = stdout
            writer = stdin
            # Read for up to ~3s and look for the alt-screen enter sequence.
            buf = ""
            try:
                for _ in range(30):
                    chunk = await asyncio.wait_for(reader.read(2048), timeout=0.2)
                    if not chunk:
                        break
                    buf += chunk
                    if "\x1b[?1049h" in buf:
                        break
            except asyncio.TimeoutError:
                pass

            assert "\x1b[?1049h" in buf, \
                f"expected alt-screen sequence in SSH output; got {buf[:500]!r}"

            # Tell the app to quit: send ctrl-c (and wait a beat)
            writer.write("\x03")
            try:
                writer.write_eof()
            except Exception:
                pass
            await asyncio.sleep(0.1)
    finally:
        acceptor.close()
        await acceptor.wait_closed()
