"""SSH server: ``enable_tui(port=8022)`` starts an asyncssh server that spawns
one Textual app per connection, each backed by its own NiceGUI client.

No authentication is required for the POC — see ``auth_callback`` for how to
tighten this up.
"""
from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any, Callable

import asyncssh

from .checker import get_logger
from .client import TuiClient, install_hooks
from .ssh_driver import SSHDriver
from .styles import browser_css

if TYPE_CHECKING:
    pass


log = get_logger()


# A registry of (path -> page_builder). The first enabled page becomes the
# default TUI page. ``enable_tui`` captures the currently-registered page
# builders from NiceGUI's ``Client.page_routes`` when the SSH server starts.
_REGISTERED_BUILDERS: dict[str, Callable[..., Any]] = {}


_AUTHORIZED_KEYS: "asyncssh.SSHAuthorizedKeys | None" = None


class _TUIServer(asyncssh.SSHServer):
    def connection_made(self, conn: asyncssh.SSHServerConnection) -> None:
        log.info("SSH connection made: %s", conn.get_extra_info("peername"))

    def begin_auth(self, username: str) -> bool:  # noqa: ARG002
        return _AUTHORIZED_KEYS is not None

    def password_auth_supported(self) -> bool:
        return False

    def public_key_auth_supported(self) -> bool:
        return _AUTHORIZED_KEYS is not None

    def validate_public_key(self, username: str, key: asyncssh.SSHKey) -> bool:  # noqa: ARG002
        if _AUTHORIZED_KEYS is None:
            return True
        return _AUTHORIZED_KEYS.validate(key, username, None, None)


async def _handle_session(process: asyncssh.SSHServerProcess) -> None:
    """Per-connection handler: build a TuiClient + Textual App, run it."""
    log.info("new TUI session")
    # Pick the first registered page builder.
    if not _REGISTERED_BUILDERS:
        process.stdout.write(
            "\r\nnicegui-tui: no @ui.page builder registered before enable_tui().\r\n"
        )
        process.exit(1)
        return

    # Prefer the '/' route when registered; otherwise fall back to the first.
    builder = _REGISTERED_BUILDERS.get("/") or next(iter(_REGISTERED_BUILDERS.values()))

    term_size = process.get_terminal_size()
    size = (term_size[0] or 80, term_size[1] or 24)

    tui_client = TuiClient(builder)

    def driver_factory(app, **kwargs):
        driver = SSHDriver(app, **kwargs)
        driver.set_process(process, size)
        # Hook PTY resize: asyncssh calls SSHServerProcess.terminal_size_changed
        # when the client sends SIGWINCH / window-change. Rebind to forward
        # into the Textual driver.
        def _on_resize(width, height, pixwidth=0, pixheight=0, *, _d=driver):
            _d.on_terminal_resize(width, height)
        try:
            process.terminal_size_changed = _on_resize  # type: ignore[method-assign]
        except Exception:
            pass
        return driver

    try:
        tui_client.build()
        app = tui_client.build_app()
        app.driver_class = driver_factory  # type: ignore[assignment]
        await app.run_async(headless=False, size=size)
    except asyncssh.BreakReceived:
        pass
    except Exception:
        log.exception("error in TUI session")
    finally:
        tui_client.dispose()
        try:
            process.exit(0)
        except Exception:
            pass


async def _start_server(port: int, host: str, host_key_path: str | None) -> asyncssh.SSHAcceptor:
    if host_key_path is None:
        # Generate an ephemeral host key in-memory. Good enough for localhost POC.
        key = asyncssh.generate_private_key("ssh-rsa")
        server_host_keys = [key]
    else:
        server_host_keys = [host_key_path]

    acceptor = await asyncssh.create_server(
        _TUIServer,
        host,
        port,
        server_host_keys=server_host_keys,
        process_factory=_handle_session,
        # Disable asyncssh's built-in line editor. With it enabled (the
        # default), the server cooks input: lines are buffered until Enter,
        # characters are echoed back to the client, and unrecognised escape
        # sequences (notably xterm mouse-report CSI bytes) are bounced
        # straight to the client's terminal. Textual needs raw byte-at-a-time
        # input and expects to own the display entirely, so we turn the
        # editor off here rather than per-channel.
        line_editor=False,
    )
    log.info("nicegui-tui SSH server listening on %s:%d", host, port)
    return acceptor


def _capture_builders() -> None:
    from nicegui.client import Client
    _REGISTERED_BUILDERS.clear()
    for builder, path in Client.page_routes.items():
        _REGISTERED_BUILDERS[path] = builder


def enable_tui(
    port: int = 8022,
    host: str = "127.0.0.1",
    host_key_path: str | None = None,
    authorized_keys: str | None = None,
) -> None:
    """Enable the TUI SSH server for this NiceGUI app.

    Call *before* ``ui.run()``. Starts an asyncssh server that listens on
    ``host:port``. Each incoming SSH session spawns a Textual app bridged to
    a fresh NiceGUI client running the app's page builder.

    :param port: TCP port to listen on (default: 8022)
    :param host: bind address (default: 127.0.0.1)
    :param host_key_path: optional path to an OpenSSH-format private key; if
        omitted, an ephemeral RSA key is generated in memory.
    :param authorized_keys: optional path to an OpenSSH authorized_keys file.
        If given, only clients with matching keys may connect (public-key
        auth). If None (default), the server accepts any connection — POC
        mode; do NOT expose beyond localhost without this.
    """
    install_hooks()

    if authorized_keys is not None:
        global _AUTHORIZED_KEYS
        _AUTHORIZED_KEYS = asyncssh.read_authorized_keys(authorized_keys)

    from nicegui import app as ng_app
    from nicegui import ui

    # Inject browser-side CSS for the tcss-* helpers and tui-only opt-out.
    # ``shared=True`` so this applies to all @ui.page endpoints from the
    # global scope (per NiceGUI's ui_run check).
    ui.add_css(browser_css(), shared=True)

    async def _startup() -> None:
        _capture_builders()
        await _start_server(port=port, host=host, host_key_path=host_key_path)

    ng_app.on_startup(_startup)
