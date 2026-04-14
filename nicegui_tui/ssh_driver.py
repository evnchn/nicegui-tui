"""Custom Textual driver that reads from and writes to asyncssh streams.

The driver runs in a single asyncio task (no threads) to avoid issues with
asyncssh's event-loop-affinity. It spawns a background task that feeds raw
input bytes through Textual's ``XTermParser`` and forwards parsed events to
the running ``App``.
"""
from __future__ import annotations

import asyncio
from codecs import getincrementaldecoder
from typing import TYPE_CHECKING, Any

import asyncssh

from textual import events
from textual._xterm_parser import XTermParser
from textual.driver import Driver
from textual.geometry import Size

if TYPE_CHECKING:
    from textual.app import App


class SSHDriver(Driver):
    """A Textual driver that sends output to an asyncssh channel."""

    def __init__(
        self,
        app: "App[Any]",
        *,
        debug: bool = False,
        mouse: bool = False,
        size: tuple[int, int] | None = None,
    ) -> None:
        # Default ``mouse=False`` for SSH. Enabling mouse tracking over
        # a remote terminal requires the client's terminal emulator to
        # cooperate; if we enable it and then fail to consume all the
        # report bytes, the client's screen fills with CSI spam. Safer
        # default: keyboard-only. Pass ``mouse=True`` explicitly to opt in.
        super().__init__(app, debug=debug, mouse=mouse, size=size or (80, 24))
        self._process: Any = None
        self._input_task: asyncio.Task | None = None
        self._closed = False
        self._loop: asyncio.AbstractEventLoop | None = None

    # The App creates the driver, but the process object is set from the outside
    # before ``run_async()`` starts the app and calls ``start_application_mode``.
    def set_process(self, process: Any, size: tuple[int, int]) -> None:
        self._process = process
        self._size = size

    def on_terminal_resize(self, width: int, height: int) -> None:
        """Called from the asyncssh process when the client resizes its PTY."""
        self._size = (width, height)
        if self._closed or self._app is None:
            return
        try:
            new_size = Size(width, height)
            self._app.post_message(events.Resize(new_size, new_size))
        except Exception:
            pass

    # -- Driver API ------------------------------------------------------

    def write(self, data: str) -> None:
        if self._closed or self._process is None:
            return
        try:
            # asyncssh's stdout.write accepts str when the session has an
            # encoding set, otherwise bytes. ``open_session`` on the server
            # side defaults to str (UTF-8) unless the caller disables it.
            self._process.stdout.write(data)
        except (BrokenPipeError, ConnectionResetError):
            self._closed = True
        except Exception:
            # Any unexpected write error means the transport is gone;
            # mark closed so we stop spamming the dead channel.
            self._closed = True

    def flush(self) -> None:
        pass

    def _write_raw(self, data: str) -> None:
        self.write(data)

    def start_application_mode(self) -> None:
        self._loop = asyncio.get_running_loop()
        # Alt screen, hide cursor, mouse support, etc.
        self.write("\x1b[?1049h")  # Alt screen
        self.write("\x1b[?25l")    # Hide cursor
        if self._mouse:
            for seq in ("\x1b[?1000h", "\x1b[?1003h", "\x1b[?1015h", "\x1b[?1006h"):
                self.write(seq)
        self.write("\x1b[?2004h")  # Bracketed paste

        size = Size(*(self._size or (80, 24)))
        self._app.post_message(events.Resize(size, size))

        self._input_task = asyncio.create_task(self._run_input_loop())

    def disable_input(self) -> None:
        if self._input_task is not None:
            self._input_task.cancel()
            self._input_task = None

    def stop_application_mode(self) -> None:
        # Emit the terminal-restore sequences BEFORE marking the driver closed,
        # otherwise write() short-circuits and the client's terminal is left in
        # alt-screen + mouse-reporting mode (visible as "garbage after quit").
        try:
            self.write("\x1b[?2004l")
            if self._mouse:
                for seq in ("\x1b[?1000l", "\x1b[?1003l", "\x1b[?1015l", "\x1b[?1006l"):
                    self.write(seq)
            self.write("\x1b[?25h")    # Show cursor
            self.write("\x1b[?1049l")  # Leave alt screen
            # asyncssh flushes automatically; drain() is a coroutine and we
            # can't await here (Textual calls stop_application_mode sync).
        except Exception:
            pass
        self._closed = True
        self.disable_input()

    def close(self) -> None:
        self._closed = True

    # -- input loop ------------------------------------------------------

    async def _run_input_loop(self) -> None:
        """Read from the SSH channel and feed parsed events to the app."""
        parser = XTermParser(debug=self._debug)
        decode = getincrementaldecoder("utf-8")().decode
        assert self._process is not None
        stdin = self._process.stdin
        try:
            while not self._closed:
                try:
                    chunk = await stdin.read(1024)
                except asyncssh.misc.BreakReceived:
                    # Client sent Ctrl-C at the SSH protocol level; exit cleanly.
                    break
                except (ConnectionResetError, EOFError):
                    break
                except Exception:
                    # Any other read error: treat as disconnect.
                    break
                if not chunk:
                    # EOF from client.
                    break
                if isinstance(chunk, bytes):
                    text = decode(chunk)
                else:
                    text = chunk
                for event in parser.feed(text):
                    self.process_message(event)
                for event in parser.tick():
                    self.process_message(event)
        except asyncio.CancelledError:
            pass
        finally:
            self._closed = True
            # Tell the app to exit. This triggers Textual to run
            # stop_application_mode (via App shutdown) and return from
            # run_async(), which lets _handle_session fall through to
            # its finally block and close the process.
            from textual import messages
            try:
                await self._app._post_message(messages.ExitApp())
            except Exception:
                pass
