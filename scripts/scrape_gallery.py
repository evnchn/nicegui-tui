"""Scrape gallery render over SSH for debugging."""
from __future__ import annotations

import asyncio
import socket
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import asyncssh  # noqa: E402

from nicegui_tui.client import install_hooks  # noqa: E402
from nicegui_tui.server import _start_server, _REGISTERED_BUILDERS  # noqa: E402


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


async def main() -> None:
    install_hooks()
    port = _free_port()

    from nicegui import ui
    state = {"count": 0}

    def index() -> None:
        ui.label("nicegui-tui gallery").classes("tcss-primary tcss-bold")
        ui.separator()
        ui.markdown("**Markdown** with *emphasis*.").classes("tcss-padded")
        ui.label("a muted label").classes("tcss-muted")
        with ui.row().classes("tcss-padded"):
            ui.button("Increment").classes("tcss-primary")
            ui.label("count: 0").classes("tcss-bold")
            ui.button("Warn").classes("tcss-warning")
            ui.button("Error").classes("tcss-danger")
        ui.button("Open dialog")

    _REGISTERED_BUILDERS.clear()
    _REGISTERED_BUILDERS["/"] = index

    acceptor = await _start_server(port=port, host="127.0.0.1", host_key_path=None)
    try:
        async with asyncssh.connect(
            "127.0.0.1", port=port, username="tui",
            known_hosts=None, client_keys=None, password=None,
        ) as conn:
            stdin, stdout, _stderr = await conn.open_session(
                command=None, term_type="xterm-256color", term_size=(120, 40),
                encoding="utf-8",
            )
            buf = ""
            deadline = asyncio.get_event_loop().time() + 2.5
            while asyncio.get_event_loop().time() < deadline:
                try:
                    chunk = await asyncio.wait_for(stdout.read(4096), timeout=0.2)
                except asyncio.TimeoutError:
                    continue
                if not chunk:
                    break
                buf += chunk
            stdin.write("\x03")
            try:
                stdin.write_eof()
            except Exception:
                pass
        Path("/tmp/gallery-render.txt").write_text(buf)
        import re
        clean = re.sub(r"\x1b\[[0-9;<>?]*[a-zA-Z]", "", buf)
        clean = re.sub(r"\x1b\][^\x07]*\x07", "", clean)
        Path("/tmp/gallery-clean.txt").write_text(clean)
        print(f"dumped {len(buf)} bytes; clean preview:")
        print(clean[:3000])
    finally:
        acceptor.close()
        await acceptor.wait_closed()


if __name__ == "__main__":
    asyncio.run(main())
