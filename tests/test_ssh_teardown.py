"""Verify the SSH driver emits terminal-restore sequences on Ctrl+Q.

Regression test: previously ``stop_application_mode`` set ``self._closed=True``
before writing the restore sequences, so ``write()`` short-circuited and the
client's terminal was left in alt-screen + mouse-reporting mode. Visible as
'garbage on terminal after quit'.
"""
from __future__ import annotations

import asyncio
import socket
import sys
from pathlib import Path

import asyncssh
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from nicegui import ui  # noqa: E402
from nicegui_tui.client import install_hooks  # noqa: E402
from nicegui_tui.server import _REGISTERED_BUILDERS, _start_server  # noqa: E402


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.mark.asyncio
async def test_ctrl_q_emits_terminal_restore_sequences() -> None:
    install_hooks()
    port = _free_port()

    def page() -> None:
        ui.label("quit-test")

    _REGISTERED_BUILDERS.clear()
    _REGISTERED_BUILDERS["/"] = page

    acceptor = await _start_server(port=port, host="127.0.0.1", host_key_path=None)
    try:
        async with asyncssh.connect(
            "127.0.0.1", port=port, username="tui",
            known_hosts=None, client_keys=None, password=None,
        ) as conn:
            stdin, stdout, _stderr = await conn.open_session(
                command=None, term_type="xterm-256color", term_size=(80, 24),
                encoding="utf-8",
            )
            # Read until we see the app rendered.
            buf = ""
            deadline = asyncio.get_event_loop().time() + 3.0
            while asyncio.get_event_loop().time() < deadline:
                try:
                    chunk = await asyncio.wait_for(stdout.read(4096), timeout=0.2)
                except asyncio.TimeoutError:
                    continue
                if not chunk:
                    break
                buf += chunk
                if "quit-test" in buf:
                    break
            assert "quit-test" in buf

            # Send Ctrl+Q — Textual's default quit binding.
            stdin.write("\x11")
            # Read whatever comes out until the channel closes.
            tail = ""
            deadline = asyncio.get_event_loop().time() + 3.0
            while asyncio.get_event_loop().time() < deadline:
                try:
                    chunk = await asyncio.wait_for(stdout.read(4096), timeout=0.2)
                except asyncio.TimeoutError:
                    continue
                if not chunk:
                    break
                tail += chunk

            assert "\x1b[?1049l" in tail, (
                f"alt-screen leave sequence missing from teardown; "
                f"tail repr={tail[-300:]!r}"
            )
            assert "\x1b[?25h" in tail, "show-cursor sequence missing"
    finally:
        acceptor.close()
        await acceptor.wait_closed()
