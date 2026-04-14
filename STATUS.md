# nicegui-tui — Status

**Built:** 2026-04-14 / 2026-04-15 overnight stretch
**Target:** Bridge NiceGUI apps to SSH-served Textual TUIs without patching NiceGUI source.

## What works

### Main goals (all done)
- `enable_tui(port=8022)` hook — no NiceGUI source edits; hooks are in-memory monkey-patches of the installed package.
- Per-SSH-connection `TuiClient` — each connection runs the registered page builder into a fresh element tree.
- 15 elements supported: `label`, `markdown`, `button`, `input`, `textarea`, `checkbox`, `switch`, `radio`, `select`, `row`, `column`, `card`, `separator`, `notify`, `dialog`.
- `tcss-*` helper classes (`tcss-border`, `tcss-padded`, `tcss-muted`, `tcss-primary`, `tcss-danger`, `tcss-success`, `tcss-warning`, `tcss-bold`) with both browser CSS defaults (auto-injected via `ui.add_css`) and TUI TCSS rules.
- Opt-out classes: `tui-hide` (skipped in TUI), `tui-only` (skipped in browser via injected CSS).
- Runtime checker: unsupported element instantiation logs `WARN nicegui_tui: <Type> not supported in TUI, rendering placeholder`.
- Element gallery demo (`examples/gallery.py`) exercising all supported elements + 2 unsupported (`ui.aggrid`, `ui.plotly`) + opt-out classes + tcss helpers.

### E2E tests (3/3 passing, ~1.1s)
1. **In-process bridge** — Textual `App.run_test()` Pilot drives a TuiClient; asserts button press mutates shared state, counter label reflects it via monkey-patched `update()`, unsupported element produces WARN, `tui-hide` invisible in TUI, `tui-only` visible in TUI.
2. **Second-session state sharing** — two independent TuiClients over same `APP_STATE` dict; first bumps counter 3×; second session renders "count: 3" on mount.
3. **Real SSH smoke** — asyncssh server started on random free port; real asyncssh client connects, opens PTY session, reads back xterm alt-screen enter sequence `\x1b[?1049h` proving Textual app actually started over SSH.

### Stretch goals (attempted)
- ✅ Static AST linter: `nicegui-tui check examples/gallery.py` flags `ui.aggrid` and `ui.plotly` as `UNSUPPORTED_ELEMENT`, framework APIs (`ui.page`, `ui.run`, `ui.timer`, …) excluded from warnings. Unknown `tcss-*` / `tui-*` classes also flagged.
- ✅ Key-based SSH auth (optional) — `enable_tui(authorized_keys="~/.ssh/authorized_keys")` enables public-key auth using `asyncssh.read_authorized_keys`. Default stays open (POC). E2E tests unchanged (still use open auth).
- ❌ Telnet — not implemented.

## Known gaps / next steps
- **Auth:** SSH server currently accepts any connection (POC as specified). Add `authorized_keys` file support before non-LAN exposure.
- **Property updates:** the monkey-patch on `Element.update` covers most mutation paths; direct prop writes (`.set_value`, `.props(...)`) are routed through that same path for covered elements, but fringe elements may need per-class hooks.
- **Textual SSH transport:** current implementation wires Textual's driver to the asyncssh PTY stream directly. Works for the alt-screen test; no stress-testing of high-churn redraws yet.
- **Dialog:** rendered via Textual `ModalScreen`; not yet auto-dismissing when NiceGUI `dialog.close()` is called from server-side.
- **Event types beyond click/change:** focus/blur/keydown/keyup not bridged.

## Architecture

```
┌─────────────────┐                    ┌──────────────────────┐
│ Browser client  │  socket.io (NiceGUI native)                │
└───────┬─────────┘                    │                      │
        │                              │  NiceGUI Client      │
        │                              │  ┌─────────────┐     │
        ├──── shared state ────────────┤  │ elements{}  │     │
        │                              │  │ slots       │     │
┌───────┴─────────┐                    │  └─────────────┘     │
│ SSH/TUI client  │  asyncssh PTY      │                      │
│ (Textual App)   │◄───────────────────┤  Monkey-patched hooks│
└─────────────────┘  TuiClient bridge  │  Element.update()    │
                                       │  handle_event()      │
                                       └──────────────────────┘
```

Element.update() is monkey-patched in memory when `enable_tui()` is called. Each TuiClient subscribes per-element-id; updates fan out to any active Textual widgets bound to that NG element. Reverse direction: Textual button press calls `ng_element.handle_event({'args': {...}})` same as NiceGUI's browser path.

## Files

```
nicegui_tui/
  __init__.py       # enable_tui export
  server.py         # asyncssh server + page-builder registry
  client.py         # TuiClient: element tree -> Textual widget tree
  widgets.py        # Element class -> Textual widget factory registry
  styles.py         # tcss-* helpers: browser CSS + TUI TCSS
  checker.py        # logger + warn_unsupported
  ssh_driver.py     # Textual Driver implementation over asyncssh PTY
  lint.py           # static AST checker, `nicegui-tui check <path>`
examples/gallery.py # element gallery demo
tests/test_e2e.py   # 3 E2E tests (all passing)
```

## How to run

```bash
cd ~/nicegui-tui
.venv/bin/python examples/gallery.py
# browser: http://localhost:8080
# TUI:     ssh localhost -p 8022  (any username, no password)

# static check
.venv/bin/nicegui-tui check examples/gallery.py

# tests
.venv/bin/python -m pytest tests/ -v
```
