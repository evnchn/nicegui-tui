"""Public-key auth via ``enable_tui(authorized_keys=...)``.

Regression test: ``validate_public_key`` returned asyncssh's options mapping,
which is ``{}`` (falsy) for a plain matching key, so every listed key was
rejected. Keys with a ``from=`` option raised instead, because the client
address was passed as ``None``.
"""
from __future__ import annotations

import socket
import sys
from pathlib import Path

import asyncssh
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from nicegui import ui  # noqa: E402
from nicegui_tui import server  # noqa: E402
from nicegui_tui.client import install_hooks  # noqa: E402


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


async def _can_login(port: int, key: asyncssh.SSHKey) -> bool:
    try:
        async with asyncssh.connect('127.0.0.1', port=port, username='tui', known_hosts=None,
                                    client_keys=[key], password=None, agent_path=None):
            return True
    except asyncssh.PermissionDenied:
        return False


@pytest.mark.asyncio
@pytest.mark.parametrize('prefix, expected', [
    ('', True),
    ('from="127.0.0.1" ', True),
    ('from="10.9.9.9" ', False),
])
async def test_authorized_keys(monkeypatch: pytest.MonkeyPatch, prefix: str, expected: bool) -> None:
    install_hooks()
    server._REGISTERED_BUILDERS.clear()
    server._REGISTERED_BUILDERS['/'] = lambda: ui.label('auth-test')
    key = asyncssh.generate_private_key('ssh-ed25519')
    stranger = asyncssh.generate_private_key('ssh-ed25519')
    keys = asyncssh.import_authorized_keys(prefix + key.export_public_key().decode())
    monkeypatch.setattr(server, '_AUTHORIZED_KEYS', keys)

    port = _free_port()
    acceptor = await server._start_server(port=port, host='127.0.0.1', host_key_path=None)
    try:
        assert await _can_login(port, key) is expected
        assert await _can_login(port, stranger) is False
    finally:
        acceptor.close()
        await acceptor.wait_closed()
