"""Manual SSH rendering smoke script.

Starts the in-process SSH server (using the demo page builder from tests) and
opens an asyncssh client with a PTY. Reads any bytes coming back for 2s and
dumps them to ``/tmp/ssh-render-dump.txt``. Then sends a keystroke, reads a
bit more, cleanly closes.

Intended for humans to diagnose "does anything render?" at a glance.
"""
from __future__ import annotations

import asyncio
import os
import socket
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import asyncssh  # noqa: E402

from nicegui import ui  # noqa: E402
from nicegui_tui.client import install_hooks  # noqa: E402
from nicegui_tui.server import _start_server, _REGISTERED_BUILDERS  # noqa: E402


OUT = Path("/tmp/ssh-render-dump.txt")


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _page() -> None:
    ui.label("Gallery").classes("tcss-primary tcss-bold")
    ui.button("bump")
    ui.label("count: 0")
    ui.input("name")


async def main() -> None:
    install_hooks()
    port = _free_port()
    _REGISTERED_BUILDERS.clear()
    _REGISTERED_BUILDERS["/"] = _page
    acceptor = await _start_server(port=port, host="127.0.0.1", host_key_path=None)
    buf = ""
    try:
        async with asyncssh.connect(
            "127.0.0.1", port=port, username="tui",
            known_hosts=None, client_keys=None, password=None,
        ) as conn:
            stdin, stdout, _stderr = await conn.open_session(
                command=None, term_type="xterm-256color", term_size=(100, 30),
                encoding="utf-8",
            )
            deadline = asyncio.get_event_loop().time() + 2.0
            while asyncio.get_event_loop().time() < deadline:
                try:
                    chunk = await asyncio.wait_for(stdout.read(4096), timeout=0.2)
                except asyncio.TimeoutError:
                    continue
                if not chunk:
                    break
                buf += chunk
            # send a ctrl-c to quit
            try:
                stdin.write("\x03")
                stdin.write_eof()
            except Exception:
                pass
            await asyncio.sleep(0.1)
    finally:
        acceptor.close()
        await acceptor.wait_closed()
    OUT.write_text(buf)
    print(f"dumped {len(buf)} bytes to {OUT}")
    # Show a stripped-text preview.
    import re
    text_only = re.sub(r"\x1b\[[\x30-\x3f]*[\x20-\x2f]*[\x40-\x7e]", "", buf)
    text_only = re.sub(r"\x1b\].*?\x07", "", text_only)
    text_only = re.sub(r"[\x00-\x08\x0b-\x1f]", "", text_only)
    print("---- text extract (first 800 chars) ----")
    print(text_only[:800])
    for marker in ("Gallery", "bump", "count:", "name"):
        print(f"  has {marker!r}: {marker in text_only}")


if __name__ == "__main__":
    asyncio.run(main())
