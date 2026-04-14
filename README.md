# nicegui-tui

Bridge a NiceGUI app to a Textual TUI served over SSH, without modifying the NiceGUI source.

```python
from nicegui import ui
from nicegui_tui import enable_tui

@ui.page('/')
def index():
    ui.label('Hello world')
    ui.button('Click me', on_click=lambda: ui.notify('clicked'))

enable_tui(port=8022)
ui.run()
```

Then `ssh localhost -p 8022` to see and interact with the same app in a terminal.

See `examples/gallery.py` for a full element gallery.
