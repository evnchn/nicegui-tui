"""Full element gallery — try both in a browser and over SSH.

Run:
    python examples/gallery.py
Then:
    - Browser: http://localhost:8080
    - TUI:     ssh -p 8022 localhost
"""
from __future__ import annotations

from nicegui import ui

from nicegui_tui import enable_tui


state = {"count": 0}


@ui.page("/")
def index() -> None:
    ui.label("nicegui-tui gallery").classes("tcss-primary tcss-bold")
    ui.markdown("Try `Ctrl+Q` to quit cleanly. Tab through the sections below.")

    with ui.tabs() as tabs:
        ui.tab("basics", label="Basics")
        ui.tab("forms", label="Forms")
        ui.tab("layout", label="Layout")
        ui.tab("dialog", label="Dialog")
        ui.tab("binding", label="Binding")
        ui.tab("routes", label="Routes")
        ui.tab("misc", label="Misc")

    with ui.tab_panels(tabs, value="basics"):

        # -- basics ------------------------------------------------------
        with ui.tab_panel("basics"):
            ui.label("Plain label").classes("tcss-primary")
            ui.label("A muted label").classes("tcss-muted")
            ui.markdown("**Markdown** parses: *italic*, `inline code`, and\n\n- bullet one\n- bullet two")
            ui.separator()
            with ui.row():
                ui.button("Increment",
                          on_click=lambda: (state.update(count=state["count"]+1),
                                             count_label.set_text(f"count: {state['count']}")))
                count_label = ui.label(f"count: {state['count']}").classes("tcss-bold")
                ui.button("Warn",
                          on_click=lambda: ui.notify("careful!", type="warning")).classes("tcss-warning")
                ui.button("Error",
                          on_click=lambda: ui.notify("bad!", type="negative")).classes("tcss-danger")
            ui.link("NiceGUI docs", "https://nicegui.io/").classes("tcss-primary")

        # -- forms (selection loopback) ---------------------------------
        with ui.tab_panel("forms"):
            ui.markdown("Every control echoes its current value to a muted label below it.")
            name = ui.input("Name", placeholder="type something")
            ui.label().bind_text_from(name, "value",
                                      backward=lambda v: f"name = {v!r}").classes("tcss-muted")

            notes = ui.textarea("Notes", placeholder="...")
            ui.label().bind_text_from(notes, "value",
                                      backward=lambda v: f"notes length = {len(v or '')}").classes("tcss-muted")

            accept = ui.checkbox("Accept terms")
            ui.label().bind_text_from(accept, "value",
                                      backward=lambda v: f"accepted = {bool(v)}").classes("tcss-muted")

            feature = ui.switch("Enable feature")
            ui.label().bind_text_from(feature, "value",
                                      backward=lambda v: f"feature = {bool(v)}").classes("tcss-muted")

            choice = ui.radio(["alpha", "beta", "gamma"], value="alpha")
            ui.label().bind_text_from(choice, "value",
                                      backward=lambda v: f"radio = {v}").classes("tcss-muted")

            color = ui.select(["red", "green", "blue"], value="red")
            ui.label().bind_text_from(color, "value",
                                      backward=lambda v: f"color = {v}").classes("tcss-muted")

        # -- layout ------------------------------------------------------
        with ui.tab_panel("layout"):
            with ui.row():
                ui.label("row-a")
                ui.label("row-b")
                ui.label("row-c")
            with ui.column():
                ui.label("col-1")
                ui.label("col-2")
            with ui.card().classes("tcss-border tcss-padded"):
                ui.label("inside a card").classes("tcss-bold")
                ui.label("with padding + border")

        # -- dialog ------------------------------------------------------
        with ui.tab_panel("dialog"):
            with ui.dialog() as dlg, ui.card():
                ui.label("This is a modal.").classes("tcss-bold")
                ui.markdown("Close it with the button below or `Esc`.")
                ui.button("Close", on_click=dlg.close)
            ui.button("Open dialog", on_click=dlg.open).classes("tcss-primary")

        # -- binding (homepage reversal) --------------------------------
        with ui.tab_panel("binding"):
            ui.markdown("NiceGUI homepage text-reversal demo: the label mirrors the input reversed.")
            src = ui.input("type here")
            ui.label().bind_text_from(
                src, "value",
                backward=lambda v: (v or "")[::-1],
            ).classes("tcss-primary tcss-bold")

        # -- routes (ui.sub_pages) --------------------------------------
        with ui.tab_panel("routes"):
            ui.markdown(
                "`ui.sub_pages` swaps content without a URL change. "
                "In the TUI, press **Ctrl+P** to pick a route."
            )

            def _home():
                ui.label("home view").classes("tcss-primary tcss-bold")
                ui.markdown("This is the `/` route.")

            def _about():
                ui.label("about view").classes("tcss-success tcss-bold")
                ui.markdown("This is the `/about` route. Press **Ctrl+P** to switch again.")

            def _settings():
                ui.label("settings view").classes("tcss-warning tcss-bold")
                with ui.card().classes("tcss-border tcss-padded"):
                    ui.checkbox("Notifications on")
                    ui.switch("Dark mode")

            ui.sub_pages({
                "/": _home,
                "/about": _about,
                "/settings": _settings,
            }).classes("tcss-padded")

        # -- misc (opt-out + unsupported) ------------------------------
        with ui.tab_panel("misc"):
            ui.markdown("Opt-out markers:")
            ui.label("visible only in TUI (tui-only)").classes("tui-only tcss-warning")
            ui.label("visible only in browser (tui-hide)").classes("tui-hide tcss-muted")
            ui.separator()
            ui.markdown("Unsupported elements render as placeholders and log `WARN`:")
            try:
                ui.aggrid({"columnDefs": [{"field": "x"}], "rowData": [{"x": 1}]})
            except Exception:
                pass
            try:
                ui.plotly({"data": [{"type": "scatter", "x": [1], "y": [1]}]})
            except Exception:
                pass


if __name__ in {"__main__", "__mp_main__"}:
    enable_tui(port=8022)
    ui.run(port=8080, reload=False, show=False)
