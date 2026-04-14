"""Factory registry: NiceGUI element class name -> Textual widget builder.

Supported subset:
    label, markdown, button, input, textarea, checkbox, switch,
    radio, select, row, column, card, separator, notify, dialog

Unsupported elements are rendered as a muted placeholder and logged.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable

from textual.containers import Horizontal, Vertical
from textual.widget import Widget
from textual.widgets import (
    Button,
    Checkbox,
    Input,
    Label,
    Markdown,
    RadioButton,
    RadioSet,
    Rule,
    Select,
    Static,
    Switch,
    TextArea,
)

from .checker import warn_unsupported
from .styles import tui_classes

if TYPE_CHECKING:
    from nicegui.element import Element


# ---------------------------------------------------------------------------
# Custom wrapper widgets so we can carry a back-reference to the NiceGUI
# element and intercept user interactions.
# ---------------------------------------------------------------------------


class BridgedMixin:
    """Attach a NiceGUI element reference to a Textual widget."""

    ng_element_id: int = -1


class NGLabel(Static, BridgedMixin):
    pass


class NGMarkdown(Markdown, BridgedMixin):
    pass


class NGButton(Button, BridgedMixin):
    pass


class NGInput(Input, BridgedMixin):
    pass


class NGTextArea(TextArea, BridgedMixin):
    pass


class NGCheckbox(Checkbox, BridgedMixin):
    pass


class NGSwitch(Switch, BridgedMixin):
    pass


class NGRadioSet(RadioSet, BridgedMixin):
    pass


class NGSelect(Select, BridgedMixin):
    pass


class NGSeparator(Rule, BridgedMixin):
    pass


class NGRow(Horizontal, BridgedMixin):
    pass


class NGColumn(Vertical, BridgedMixin):
    pass


class NGCard(Vertical, BridgedMixin):
    pass


class NGPlaceholder(Static, BridgedMixin):
    pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _apply_common(widget: Widget, element: "Element") -> Widget:
    """Apply id, classes, and hide-visibility rules from a NiceGUI element."""
    widget.ng_element_id = element.id  # type: ignore[attr-defined]
    classes = list(getattr(element, "_classes", []) or [])
    for c in tui_classes(classes):
        widget.add_class(c)
    if not getattr(element, "visible", True):
        widget.display = False
    return widget


def _text_of(element: "Element") -> str:
    return (element._text or "") if element._text is not None else ""


# ---------------------------------------------------------------------------
# Factories. Each returns a Textual widget (possibly a container to be
# populated with children by the caller).
# ---------------------------------------------------------------------------


def _make_label(element: "Element") -> Widget:
    w = NGLabel(_text_of(element))
    w.styles.width = "auto"
    w.styles.height = "auto"
    return _apply_common(w, element)


def _make_markdown(element: "Element") -> Widget:
    # ui.markdown stores content on the element; fall back to text
    content = getattr(element, "content", None) or _text_of(element)
    return _apply_common(NGMarkdown(content), element)


def _make_button(element: "Element") -> Widget:
    label = element._props.get("label", "") or _text_of(element) or "Button"
    w = NGButton(str(label))
    return _apply_common(w, element)


def _make_input(element: "Element") -> Widget:
    value = element._props.get("value", "") or ""
    placeholder = element._props.get("placeholder", "") or ""
    label = element._props.get("label") or ""
    password = element._props.get("type") == "password"
    w = NGInput(value=str(value), placeholder=str(placeholder), password=password)
    if label:
        w.border_title = str(label)
    return _apply_common(w, element)


def _make_textarea(element: "Element") -> Widget:
    value = element._props.get("value", "") or ""
    w = NGTextArea(str(value))
    w.styles.height = 6
    label = element._props.get("label")
    if label:
        w.border_title = str(label)
    return _apply_common(w, element)


def _make_checkbox(element: "Element") -> Widget:
    label = _text_of(element) or ""
    value = bool(element._props.get("model-value", False))
    w = NGCheckbox(label, value=value)
    return _apply_common(w, element)


def _make_switch(element: "Element") -> Widget:
    value = bool(element._props.get("model-value", False))
    w = NGSwitch(value=value)
    # Switch doesn't carry a label; add sibling text if present.
    label = _text_of(element) or ""
    if label:
        w.tooltip = label
    return _apply_common(w, element)


def _make_radio(element: "Element") -> Widget:
    labels = getattr(element, "_labels", None) or []
    if not labels:
        options = element._props.get("options", [])
        labels = [str(o.get("label", o) if isinstance(o, dict) else o) for o in options]
    current_index = element._props.get("model-value")
    buttons = []
    for i, lbl in enumerate(labels):
        buttons.append(RadioButton(str(lbl), value=(i == current_index)))
    w = NGRadioSet(*buttons)
    return _apply_common(w, element)


def _make_select(element: "Element") -> Widget:
    labels = getattr(element, "_labels", None) or []
    if not labels:
        options = element._props.get("options", [])
        labels = [str(o.get("label", o) if isinstance(o, dict) else o) for o in options]
    if not labels:
        labels = [""]
    pairs = [(str(lbl), i) for i, lbl in enumerate(labels)]
    current_index = None
    mv = element._props.get("model-value")
    if isinstance(mv, dict):
        current_index = mv.get("value")
    value = current_index if current_index is not None else Select.BLANK
    w = NGSelect(options=pairs, value=value, allow_blank=True)
    return _apply_common(w, element)


def _make_separator(element: "Element") -> Widget:
    return _apply_common(NGSeparator(), element)


def _make_row(element: "Element") -> Widget:
    w = NGRow()
    w.styles.height = "auto"
    return _apply_common(w, element)


def _make_column(element: "Element") -> Widget:
    w = NGColumn()
    w.styles.height = "auto"
    return _apply_common(w, element)


def _make_card(element: "Element") -> Widget:
    w = NGCard()
    w.styles.height = "auto"
    w.styles.border = ("round", "grey")
    w.styles.padding = (0, 1)
    return _apply_common(w, element)


def _make_dialog(element: "Element") -> Widget:
    # Render dialog as a collapsible card in the TUI. It's shown inline
    # regardless of its open/closed state — sufficient for the POC.
    w = NGCard()
    w.styles.height = "auto"
    w.styles.border = ("double", "magenta")
    w.border_title = "Dialog"
    return _apply_common(w, element)


def _make_placeholder(element: "Element") -> Widget:
    type_name = type(element).__name__
    w = NGPlaceholder(f"[unsupported: {type_name}]")
    w.add_class("tcss-muted")
    return _apply_common(w, element)


# Key = NiceGUI element class name (no imports needed at module-load time).
FACTORIES: dict[str, Callable[[Any], Widget]] = {
    "Label": _make_label,
    "Markdown": _make_markdown,
    "Button": _make_button,
    "Input": _make_input,
    "Textarea": _make_textarea,
    "Checkbox": _make_checkbox,
    "Switch": _make_switch,
    "Radio": _make_radio,
    "Select": _make_select,
    "Separator": _make_separator,
    "Row": _make_row,
    "Column": _make_column,
    "Card": _make_card,
    "Dialog": _make_dialog,
    "Notification": _make_label,  # rendered as a small label; see server.py for toasts
}

# ``ui.notify`` is a function, not an element — it's handled by intercepting
# outbox messages in the client module.

# These NiceGUI container elements are created implicitly by the framework but
# aren't part of the user-facing API; skip rendering them and let their children
# bubble up.
INVISIBLE_TYPES = {"QLayout", "QPageContainer", "QPage", "SubPages"}


def supported_types() -> set[str]:
    return set(FACTORIES.keys())


def build_widget(element: "Element") -> Widget:
    """Return a Textual widget for the given NiceGUI element.

    Unknown types get a placeholder + a one-time warning log.
    """
    name = type(element).__name__
    factory = FACTORIES.get(name)
    if factory is None:
        warn_unsupported(element)
        return _make_placeholder(element)
    return factory(element)
