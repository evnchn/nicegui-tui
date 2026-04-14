"""Full element gallery — try both in a browser and over SSH.

Run:
    python examples/gallery.py
Then:
    - Browser: http://localhost:8080
    - TUI:     ssh localhost -p 8022
"""
from __future__ import annotations

from nicegui import ui

from nicegui_tui import enable_tui


state = {"count": 0, "last_input": "", "accepted": False}


@ui.page("/")
def index() -> None:
    ui.label("nicegui-tui gallery").classes("tcss-primary tcss-bold")
    ui.separator()

    # --- text / markdown -----------------------------------------------
    ui.markdown("**Markdown** with *emphasis* and `code`.").classes("tcss-padded")
    ui.label("a muted label").classes("tcss-muted")

    # --- buttons --------------------------------------------------------
    with ui.row().classes("tcss-padded"):
        ui.button("Increment", on_click=lambda: _bump()).classes("tcss-primary")
        count_label = ui.label("count: 0").classes("tcss-bold")
        ui.button("Warn", on_click=lambda: ui.notify("careful!", type="warning")).classes("tcss-warning")
        ui.button("Error", on_click=lambda: ui.notify("bad!", type="negative")).classes("tcss-danger")

    def _bump() -> None:
        state["count"] += 1
        count_label.set_text(f"count: {state['count']}")

    # --- form controls with selection loopback --------------------------
    # Each control echoes its current value to a label via bind_text_from.
    with ui.card().classes("tcss-border tcss-padded"):
        ui.label("Form controls (each echoes into a label)").classes("tcss-bold")

        name = ui.input("Name", placeholder="type something")
        ui.label().bind_text_from(name, "value", backward=lambda v: f"name = {v!r}").classes("tcss-muted")

        notes = ui.textarea("Notes", placeholder="...")
        ui.label().bind_text_from(notes, "value", backward=lambda v: f"notes length = {len(v or '')}").classes("tcss-muted")

        accept = ui.checkbox("Accept terms")
        ui.label().bind_text_from(accept, "value", backward=lambda v: f"accepted = {bool(v)}").classes("tcss-muted")

        feature = ui.switch("Enable feature")
        ui.label().bind_text_from(feature, "value", backward=lambda v: f"feature = {bool(v)}").classes("tcss-muted")

        choice = ui.radio(["alpha", "beta", "gamma"], value="alpha")
        ui.label().bind_text_from(choice, "value", backward=lambda v: f"radio = {v}").classes("tcss-muted")

        color = ui.select(["red", "green", "blue"], value="red")
        ui.label().bind_text_from(color, "value", backward=lambda v: f"color = {v}").classes("tcss-muted")

    # --- layout ---------------------------------------------------------
    with ui.column().classes("tcss-padded"):
        ui.label("Columned content").classes("tcss-success")

    # --- bindings (NiceGUI homepage text-reversal example) -------------
    with ui.card().classes("tcss-border tcss-padded"):
        ui.label("Binding demo: type, the reversal follows").classes("tcss-bold")
        reversed_source = ui.input("type here")
        ui.label().bind_text_from(
            reversed_source, "value",
            backward=lambda v: (v or "")[::-1],
        ).classes("tcss-primary")

    # --- dialog ---------------------------------------------------------
    with ui.dialog() as dlg, ui.card():
        ui.label("This is a dialog").classes("tcss-bold")
        ui.button("Close", on_click=dlg.close)
    ui.button("Open dialog", on_click=dlg.open)

    # --- opt-out classes ------------------------------------------------
    ui.label("only in TUI").classes("tui-only tcss-warning")
    ui.label("only in browser").classes("tui-hide tcss-muted")

    # --- unsupported elements (should log WARN + render placeholder) ----
    try:
        ui.aggrid({"columnDefs": [{"field": "x"}], "rowData": [{"x": 1}]})
    except Exception:  # pragma: no cover
        pass
    try:
        ui.plotly({"data": [{"type": "scatter", "x": [1], "y": [1]}]})
    except Exception:  # pragma: no cover
        pass


if __name__ in {"__main__", "__mp_main__"}:
    enable_tui(port=8022)
    ui.run(port=8080, reload=False, show=False)
