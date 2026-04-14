"""Real end-to-end SSH test: verify widgets actually render and keystrokes
reach the Textual app.

This sits alongside the existing ``test_ssh_server_accepts_connection_and_launches_tui``
smoke test and is strictly stronger:

* Starts the real asyncssh server (same fixture pattern).
* Connects with asyncssh's client and a PTY.
* Reads the output stream until *widget content bytes* (e.g. ``Gallery`` or
  ``bump``) appear, rather than just the alt-screen enter sequence. This is
  the check the existing smoke test was missing — alt-screen enter is emitted
  by ``start_application_mode`` before the first render, so an app that never
  renders a single frame still passes the old test.
* Sends keystrokes (Tab/Enter) that should focus the ``bump`` button and
  activate it. Asserts shared Python-side state mutated — meaning input
  bytes round-tripped through the driver's parser, Textual dispatched a
  Button.Pressed, and the NiceGUI click handler fired.
* Closes cleanly.
"""
from __future__ import annotations

import asyncio
import re
import socket
import sys
from pathlib import Path

import asyncssh
import pytest
import pytest_asyncio

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from nicegui import ui  # noqa: E402
from nicegui_tui.checker import reset_warnings  # noqa: E402
from nicegui_tui.client import install_hooks  # noqa: E402
from nicegui_tui.server import _start_server, _REGISTERED_BUILDERS  # noqa: E402


APP_STATE: dict[str, int] = {"count": 0}


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _strip_ansi(buf: str) -> str:
    """Crude ANSI/escape stripper good enough for content-matching."""
    buf = re.sub(r"\x1b\][^\x07]*(?:\x07|\x1b\\)", "", buf)  # OSC
    buf = re.sub(r"\x1b\[[\x30-\x3f]*[\x20-\x2f]*[\x40-\x7e]", "", buf)  # CSI
    buf = re.sub(r"\x1b[PX^_][^\x1b]*\x1b\\", "", buf)  # DCS/PM/APC/SOS
    buf = re.sub(r"\x1b[=>78cDEHMZ]", "", buf)  # misc ESC single-char
    buf = re.sub(r"[\x00-\x08\x0b-\x1f]", "", buf)
    return buf


def _page_builder() -> None:
    def bump() -> None:
        APP_STATE["count"] += 1
        counter.set_text(f"count: {APP_STATE['count']}")

    ui.label("Gallery")
    btn = ui.button("bump", on_click=bump)
    btn.mark("bump-btn")
    counter = ui.label(f"count: {APP_STATE['count']}")


@pytest_asyncio.fixture(autouse=True)
async def _setup():
    install_hooks()
    reset_warnings()
    APP_STATE["count"] = 0
    yield


async def _read_until(reader, marker: str, deadline: float) -> str:
    """Read from ``reader`` until ``marker`` appears in the stripped-ANSI
    text view, or ``deadline`` (absolute loop time) expires."""
    buf = ""
    loop = asyncio.get_event_loop()
    while loop.time() < deadline:
        try:
            chunk = await asyncio.wait_for(
                reader.read(4096), timeout=max(0.05, deadline - loop.time())
            )
        except asyncio.TimeoutError:
            break
        if not chunk:
            break
        buf += chunk
        if marker in _strip_ansi(buf):
            return buf
    return buf


@pytest.mark.asyncio
async def test_ssh_renders_and_handles_keystrokes() -> None:
    port = _free_port()
    _REGISTERED_BUILDERS.clear()
    _REGISTERED_BUILDERS["/"] = _page_builder

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
            stdin, stdout, _stderr = await conn.open_session(
                command=None,
                term_type="xterm-256color",
                term_size=(100, 30),
                encoding="utf-8",
            )
            loop = asyncio.get_event_loop()

            # Phase 1: widget content must reach us.
            buf1 = await _read_until(stdout, "Gallery", loop.time() + 3.0)
            text1 = _strip_ansi(buf1)
            assert "Gallery" in text1, (
                "did not see widget label text over SSH; "
                f"raw head={buf1[:400]!r}, stripped head={text1[:400]!r}"
            )
            assert "bump" in text1, (
                f"missing button label; stripped head={text1[:400]!r}"
            )
            assert "count: 0" in text1, (
                f"missing counter label; stripped head={text1[:400]!r}"
            )

            # Phase 2: focus the button and activate it.
            # Tab should focus the first focusable widget (the button, since
            # the label isn't focusable). Enter presses it.
            stdin.write("\t")
            await asyncio.sleep(0.15)
            stdin.write("\r")
            # Keep draining so the render pipeline flushes.
            await _read_until(stdout, "count: 1", loop.time() + 2.0)

            assert APP_STATE["count"] >= 1, (
                f"button activation did not fire handler; APP_STATE={APP_STATE}"
            )

            # Clean close.
            try:
                stdin.write_eof()
            except Exception:
                pass
            await asyncio.sleep(0.1)
    finally:
        acceptor.close()
        await acceptor.wait_closed()
