"""TuiClient: one SSH connection = one NiceGUI Client rendered in Textual.

Responsibilities:
    - Create a fresh ``nicegui.Client`` and run the registered page builder
      inside it, so elements instantiate into ``client.elements``.
    - Walk the element tree and build a matching Textual widget tree.
    - Observe element updates (via a monkey-patched ``Element.update``) and
      reflect changed props back into the corresponding Textual widget.
    - Translate Textual widget events (button press, input change, etc.) into
      NiceGUI's native event dispatch (``Element._handle_event``).
    - Handle ``ui.notify`` messages routed through ``client.outbox``.
"""
from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any, Callable

from textual.app import App, ComposeResult
from textual.containers import Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widget import Widget
from textual.widgets import Button, Checkbox, Input, RadioSet, Select, Static, Switch, TextArea

from .checker import get_logger
from .styles import tui_tcss
from .widgets import (
    BridgedMixin,
    INVISIBLE_TYPES,
    NGCheckbox,
    NGInput,
    NGRadioSet,
    NGSelect,
    NGSwitch,
    NGTextArea,
    build_widget,
)

if TYPE_CHECKING:
    from nicegui.client import Client
    from nicegui.element import Element


log = get_logger()


# ---------------------------------------------------------------------------
# Monkey-patch: observe Element.update() and Client.outbox.enqueue_message
# ---------------------------------------------------------------------------

_PATCHED = False
_OBSERVERS: dict[int, list["TuiClient"]] = {}
_NOTIFY_OBSERVERS: dict[str, list["TuiClient"]] = {}


def install_hooks() -> None:
    """Install the global observation hooks on the installed NiceGUI package."""
    global _PATCHED
    if _PATCHED:
        return

    from nicegui.element import Element
    from nicegui.outbox import Outbox

    original_update = Element.update

    def patched_update(self: "Element") -> None:
        original_update(self)
        try:
            cid = id(self.client)
        except Exception:
            return
        for obs in _OBSERVERS.get(cid, ()):
            obs.notify_element_changed(self)

    Element.update = patched_update  # type: ignore[assignment]

    original_enqueue_message = Outbox.enqueue_message

    def patched_enqueue_message(self: "Outbox", name: str, data: Any, target_id: str) -> None:
        original_enqueue_message(self, name, data, target_id)
        if name == "notify":
            client_pyid = id(self.client)
            for obs in _OBSERVERS.get(client_pyid, ()):
                obs.notify_toast(data)

    Outbox.enqueue_message = patched_enqueue_message  # type: ignore[assignment]

    _PATCHED = True


# ---------------------------------------------------------------------------
# Textual App
# ---------------------------------------------------------------------------


class TuiApp(App):
    """Textual app rendering a NiceGUI client."""

    CSS = tui_tcss()

    def __init__(self, tui_client: "TuiClient", **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._tui_client = tui_client

    def compose(self) -> ComposeResult:
        yield VerticalScroll(id="ng-root")

    async def on_mount(self) -> None:
        root = self.query_one("#ng-root", VerticalScroll)
        client = self._tui_client.ng_client
        self._tui_client._widgets.clear()
        # Mount the page's visible content in the scrollable root.
        for child in _iter_renderable(client.content):
            widget = self._tui_client._build_tree(child)
            if widget is not None:
                root.mount(widget)
        # Also register dialogs (which live as children of ``layout`` rather
        # than ``content``) so notify_element_changed can open them on demand.
        content_id = client.content.id
        for child in _iter_renderable(client.layout):
            if child.id == content_id:
                continue
            sentinel = self._tui_client._build_tree(child)
            if sentinel is not None:
                sentinel.display = False
                root.mount(sentinel)

    # -- event handlers: bridge Textual events back to NiceGUI -------------

    def on_button_pressed(self, event: Button.Pressed) -> None:
        el = self._tui_client._element_for_widget(event.button)
        if el is not None:
            self._tui_client._fire_event(el, "click", [])

    def on_input_changed(self, event: Input.Changed) -> None:
        el = self._tui_client._element_for_widget(event.input)
        if el is not None:
            self._tui_client._fire_update_model_value(el, event.value)

    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        el = self._tui_client._element_for_widget(event.text_area)
        if el is not None:
            self._tui_client._fire_update_model_value(el, event.text_area.text)

    def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        el = self._tui_client._element_for_widget(event.checkbox)
        if el is not None:
            self._tui_client._fire_update_model_value(el, bool(event.value))

    def on_switch_changed(self, event: Switch.Changed) -> None:
        el = self._tui_client._element_for_widget(event.switch)
        if el is not None:
            self._tui_client._fire_update_model_value(el, bool(event.value))

    def on_radio_set_changed(self, event: RadioSet.Changed) -> None:
        el = self._tui_client._element_for_widget(event.radio_set)
        if el is not None:
            self._tui_client._fire_update_model_value(el, event.index)

    def on_select_changed(self, event: Select.Changed) -> None:
        el = self._tui_client._element_for_widget(event.select)
        if el is not None and event.value is not Select.BLANK:
            self._tui_client._fire_update_model_value(el, {"value": event.value})


# ---------------------------------------------------------------------------
# TuiClient
# ---------------------------------------------------------------------------


def _iter_renderable(element: "Element"):
    """Yield children of an element, skipping nicegui's invisible wrappers."""
    for slot in element.slots.values():
        for child in slot.children:
            if type(child).__name__ in INVISIBLE_TYPES:
                yield from _iter_renderable(child)
            else:
                yield child


class TuiClient:
    """One NiceGUI client + one Textual app, bridged."""

    def __init__(self, page_builder: Callable[..., Any]) -> None:
        self._page_builder = page_builder
        self.ng_client = None  # type: ignore[assignment]
        self.app: TuiApp | None = None
        self._widgets: dict[int, Widget] = {}
        self._pending_updates: list[int] = []
        self._dialog_elements: dict[int, "Element"] = {}
        self._open_dialog_screens: dict[int, ModalScreen] = {}

    # -- lifecycle --------------------------------------------------------

    def build(self) -> None:
        """Create a fresh NiceGUI client and run the page builder."""
        install_hooks()
        from nicegui.client import Client
        from nicegui.page import page as page_cls

        # Build a fake ``page`` wrapper without using the decorator machinery.
        dummy_page = page_cls("/__tui__/")
        client = Client(dummy_page)
        self.ng_client = client
        _OBSERVERS.setdefault(id(client), []).append(self)

        # Run the user's page builder inside this client's element context.
        with client:
            result = self._page_builder()
            if asyncio.iscoroutine(result):
                # Best-effort: schedule but don't block here; most demos are sync.
                loop = asyncio.get_event_loop()
                loop.create_task(result)  # type: ignore[arg-type]

    def build_app(self) -> TuiApp:
        if self.ng_client is None:
            self.build()
        self.app = TuiApp(self)
        return self.app

    def dispose(self) -> None:
        if self.ng_client is not None:
            obs_list = _OBSERVERS.get(id(self.ng_client), [])
            if self in obs_list:
                obs_list.remove(self)
            try:
                self.ng_client.delete()
            except Exception:
                log.exception("error while deleting nicegui client")
            self.ng_client = None

    # -- tree construction ------------------------------------------------

    def _build_tree(self, element: "Element") -> Widget | None:
        classes = list(getattr(element, "_classes", []) or [])
        if "tui-hide" in classes:
            return None
        if "tui-only" in classes:
            pass  # tui-only: render it in TUI (and browser CSS hides it)
        # Dialogs are not mounted inline; they become ModalScreens on demand.
        if type(element).__name__ == "Dialog":
            self._dialog_elements[element.id] = element
            sentinel = Static("", id=f"ng-dialog-sentinel-{element.id}")
            sentinel.display = False
            sentinel.ng_element_id = element.id  # type: ignore[attr-defined]
            self._widgets[element.id] = sentinel
            return sentinel
        widget = build_widget(element)
        self._widgets[element.id] = widget
        # Recurse into default-slot children for containers.
        if type(element).__name__ in ("Row", "Column", "Card") or \
                type(element).__name__ in INVISIBLE_TYPES:
            for child in _iter_renderable(element):
                sub = self._build_tree(child)
                if sub is not None:
                    # Mount pending children when the widget is mounted.
                    widget._pending_children = getattr(widget, "_pending_children", [])
                    widget._pending_children.append(sub)

            def _mount_children(w=widget):
                for c in getattr(w, "_pending_children", []):
                    try:
                        w.mount(c)
                    except Exception:
                        pass
            widget.call_after_refresh(_mount_children)  # type: ignore[attr-defined]
        return widget

    def _element_for_widget(self, widget: Widget) -> "Element | None":
        eid = getattr(widget, "ng_element_id", -1)
        if eid < 0 or self.ng_client is None:
            return None
        return self.ng_client.elements.get(eid)

    # -- observer callbacks ----------------------------------------------

    def notify_element_changed(self, element: "Element") -> None:
        """Called from the patched ``Element.update``. Reflect prop/text
        changes into the corresponding Textual widget.
        """
        if self.app is None:
            return
        widget = self._widgets.get(element.id)
        if widget is None:
            return
        try:
            self._apply_element_state(widget, element)
        except Exception:
            log.exception("failed to apply element state")

    def _apply_element_state(self, widget: Widget, element: "Element") -> None:
        name = type(element).__name__
        if name == "Label":
            widget.update(element._text or "")  # type: ignore[attr-defined]
        elif name == "Markdown":
            content = getattr(element, "content", None) or (element._text or "")
            widget.update(content)  # type: ignore[attr-defined]
        elif name == "Button":
            label = element._props.get("label", "") or ""
            widget.label = str(label)  # type: ignore[attr-defined]
        elif name == "Input" and isinstance(widget, NGInput):
            val = str(element._props.get("value", "") or "")
            if widget.value != val:
                widget.value = val
        elif name == "Textarea" and isinstance(widget, NGTextArea):
            val = str(element._props.get("value", "") or "")
            if widget.text != val:
                widget.load_text(val)
        elif name == "Checkbox" and isinstance(widget, NGCheckbox):
            widget.value = bool(element._props.get("model-value", False))
        elif name == "Switch" and isinstance(widget, NGSwitch):
            widget.value = bool(element._props.get("model-value", False))
        elif name == "Dialog":
            self._sync_dialog(element)
            return  # sentinel stays hidden regardless of visibility
        # visibility
        widget.display = bool(getattr(element, "visible", True))

    def _sync_dialog(self, element: "Element") -> None:
        """Open/close a Textual ModalScreen to mirror the dialog's value prop."""
        if self.app is None:
            return
        want_open = bool(element._props.get("model-value", False))
        is_open = element.id in self._open_dialog_screens
        if want_open and not is_open:
            self._push_dialog_screen(element)
        elif not want_open and is_open:
            self._pop_dialog_screen(element)

    def _push_dialog_screen(self, element: "Element") -> None:
        tc = self
        class _DialogScreen(ModalScreen):
            DEFAULT_CSS = """
            _DialogScreen {
                align: center middle;
            }
            _DialogScreen > Vertical {
                width: auto;
                max-width: 80%;
                height: auto;
                max-height: 80%;
                border: double $accent;
                padding: 1 2;
                background: $surface;
            }
            """

            def compose(self) -> ComposeResult:
                body = Vertical()
                yield body

            def on_mount(self_s) -> None:  # type: ignore[override]
                body = self_s.query_one(Vertical)
                for child in _iter_renderable(element):
                    w = tc._build_tree(child)
                    if w is not None:
                        body.mount(w)
                        for pending in getattr(w, "_pending_children", []):
                            try:
                                w.mount(pending)
                            except Exception:
                                pass

        screen = _DialogScreen()
        self._open_dialog_screens[element.id] = screen
        self.app.push_screen(screen)

    def _pop_dialog_screen(self, element: "Element") -> None:
        screen = self._open_dialog_screens.pop(element.id, None)
        if screen is None or self.app is None:
            return
        try:
            self.app.pop_screen()
        except Exception:
            pass

    def notify_toast(self, data: dict) -> None:
        """Called for ui.notify messages on this client."""
        if self.app is None:
            return
        msg = str(data.get("message", ""))
        severity_map = {
            "positive": "information",
            "negative": "error",
            "warning": "warning",
            "info": "information",
            "ongoing": "information",
        }
        sev = severity_map.get(str(data.get("type") or ""), "information")
        try:
            self.app.call_from_thread(self.app.notify, msg, severity=sev)
        except Exception:
            try:
                self.app.notify(msg, severity=sev)  # type: ignore[arg-type]
            except Exception:
                pass

    # -- event firing -----------------------------------------------------

    def _fire_event(self, element: "Element", event_type: str, args: list) -> None:
        """Invoke the NiceGUI event handler for the given element + type."""
        from nicegui import events as ng_events

        matching = [l for l in element._event_listeners.values() if l.type == event_type]
        if not matching:
            return
        listener = matching[0]
        msg = {"listener_id": listener.id, "args": args}
        try:
            element._handle_event(msg)  # pylint: disable=protected-access
        except Exception:
            log.exception("error dispatching %s event", event_type)

    def _fire_update_model_value(self, element: "Element", value: Any) -> None:
        """Dispatch the ``update:<model-prop>`` event NiceGUI uses for two-way
        bindings on Quasar components (input, checkbox, switch, radio, select).

        The listener is registered with the raw ``update:<prop>`` type — we
        match that string directly rather than trying to camel-case it.
        """
        from nicegui.elements.mixins.value_element import ValueElement

        if isinstance(element, ValueElement):
            # NiceGUI registers the listener with the camelCased prop name:
            # 'model-value' -> 'update:modelValue', 'value' -> 'update:value'.
            parts = element.VALUE_PROP.split("-")
            camel = parts[0] + "".join(p.capitalize() for p in parts[1:])
            target_type = f"update:{camel}"
            matching = [l for l in element._event_listeners.values() if l.type == target_type]
            if matching:
                listener = matching[0]
                element._handle_event({"listener_id": listener.id, "args": value})
                # Drive NiceGUI's binding propagation synchronously so label
                # bindings (``bind_text_from``, etc.) refresh immediately
                # rather than waiting for the 100 ms refresh_loop tick.
                try:
                    from nicegui import binding as ng_binding
                    ng_binding._refresh_step()
                except Exception:
                    pass
                return
        # Fallback: try a plain 'change' event.
        self._fire_event(element, "change", [value])
