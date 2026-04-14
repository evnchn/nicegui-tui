# nicegui-tui

Serve a running NiceGUI app as a Textual TUI over SSH. No fork of NiceGUI, no app rewrite — add two lines.

```python
from nicegui import ui
from nicegui_tui import enable_tui

@ui.page('/')
def index():
    ui.label('Hello world')
    ui.button('Click', on_click=lambda: ui.notify('clicked'))

enable_tui(port=8022)
ui.run(port=8080)
```

```bash
pip install -e .          # from this repo
python your_app.py
# browser: http://localhost:8080
ssh -p 8022 -o StrictHostKeyChecking=no tui@localhost
```

## What works

Shared element tree between browser clients and SSH clients. Both see the same Python state, events on one propagate to the other.

**Elements (~20):** `label` · `markdown` (parsed) · `button` · `input` · `textarea` · `checkbox` · `switch` · `radio` · `select` · `row` · `column` · `card` · `separator` · `notify` (toast) · `dialog` (ModalScreen) · `link` · `tabs` / `tab` / `tab_panels` / `tab_panel` (Textual TabbedContent) · `sub_pages`.

**Bindings:** `bind_text_from`, `bind_value_from`, `bind_value` — propagate live across browser and TUI.

**Styling:** a small `tcss-*` helper-class vocabulary with defaults in both browser CSS and Textual TCSS. No Tailwind translation. Browser-only elements use `.classes('tui-hide')`; TUI-only use `.classes('tui-only')`.

**Routing:** `ui.sub_pages({...})` is the primary nav primitive in TUI. Press **Ctrl+P** for a route picker.

**Lifecycle:**
- **Ctrl+Q** — clean exit; alt-screen / cursor / mouse all restored.
- Terminal resize — forwarded as `Resize` events.
- SSH disconnect — NiceGUI client torn down.

## What's out of scope

- Charts (`ui.plotly`, `ui.echart`, `ui.highchart`, `ui.matplotlib`)
- Grids (`ui.aggrid`)
- Media (`ui.video`, `ui.audio`, `ui.interactive_image`, `ui.scene`)
- Rich editors (`ui.codemirror`, `ui.json_editor`)
- `ui.html` with arbitrary HTML
- Custom Vue / AnyWidget components
- Drag/drop, file upload
- Browser-native links over SSH
- Tailwind classes (drop silently; use `tcss-*` instead)

Unsupported elements render as `[unsupported: <Type>]` placeholders and log `WARN nicegui_tui:`.

## Checking TUI compatibility

Static AST check:

```bash
nicegui-tui check your_app.py
```

Flags `ui.xxx` calls outside the supported subset and unknown `tcss-*` / `tui-*` classes.

## Auth

Open by default (POC). Opt into key auth:

```python
enable_tui(port=8022, authorized_keys='~/.ssh/authorized_keys')
```

## How it works

A second `Client` is created per SSH connection, running the same `@ui.page` builder. In-memory monkey-patches observe `Element.update()` and `Outbox.enqueue_message` to reflect prop/text changes into Textual widgets. Reverse direction: Textual events (button press, input change, modal nav) are dispatched through NiceGUI's native `_handle_event`, so user-defined Python handlers run identically from both transports.

No patches on disk. Uninstall `nicegui-tui` and your app is unaffected.

## Styling palette

```
tcss-border  tcss-padded  tcss-muted   tcss-primary
tcss-danger  tcss-success tcss-warning tcss-bold
```

Add more in `nicegui_tui/styles.py`.

## Tests

```bash
.venv/bin/python -m pytest tests/ -v
```

Covers in-process bridge, real SSH render + keystroke round-trip, Ctrl+Q teardown, dialog ModalScreen, binding propagation, loopback bindings (checkbox/switch/radio/select), markdown parsing, tabs, sub_pages, route preference.

## Known limits

See `STATUS.md` for a running list.
