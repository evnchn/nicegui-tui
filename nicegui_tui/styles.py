"""tcss-* helper classes: browser CSS injection + TUI TCSS.

Ship ~8 classes that work in both the browser (via ``ui.add_css``) and in the
TUI (via Textual's CSS). Users write plain ``tcss-border``/etc. on any element.
"""
from __future__ import annotations

# Browser-side CSS. Kept deliberately small so it reads well both in a browser
# and translates conceptually to TCSS below.
BROWSER_CSS = """
.tcss-border { border: 1px solid #888; padding: 4px; border-radius: 4px; }
.tcss-padded { padding: 8px; }
.tcss-muted { color: #888; }
.tcss-primary { color: #1976d2; font-weight: 600; }
.tcss-danger { color: #c62828; font-weight: 600; }
.tcss-success { color: #2e7d32; font-weight: 600; }
.tcss-warning { color: #f9a825; font-weight: 600; }
.tcss-bold { font-weight: 700; }
/* opt-out classes */
.tui-only { display: none !important; }
"""

# Textual CSS (TCSS). Textual CSS uses a different syntax; these class-based
# selectors target widgets that had the matching class added via ``classes="..."``.
TUI_TCSS = """
.tcss-border {
    border: round $primary-lighten-2;
    padding: 0 1;
}
.tcss-padded {
    padding: 1 2;
}
.tcss-muted {
    color: $text-muted;
}
.tcss-primary {
    color: $primary;
    text-style: bold;
}
.tcss-danger {
    color: $error;
    text-style: bold;
}
.tcss-success {
    color: $success;
    text-style: bold;
}
.tcss-warning {
    color: $warning;
    text-style: bold;
}
.tcss-bold {
    text-style: bold;
}
"""


def browser_css() -> str:
    """Return the browser-side CSS to inject via ``ui.add_css``."""
    return BROWSER_CSS


def tui_tcss() -> str:
    """Return the TCSS stylesheet string to feed to the Textual App."""
    return TUI_TCSS


KNOWN_CLASSES = {
    "tcss-border", "tcss-padded", "tcss-muted", "tcss-primary",
    "tcss-danger", "tcss-success", "tcss-warning", "tcss-bold",
    "tui-only", "tui-hide",
}


def tui_classes(classes: list[str]) -> list[str]:
    """Filter a NiceGUI element's class list down to the tcss-* helpers we
    recognise. Unknown classes (e.g. Tailwind) are dropped — we don't parse them.
    Opt-out markers ``tui-only`` and ``tui-hide`` are not applied as widget
    classes; they're handled at render time.
    """
    return [c for c in classes if c.startswith("tcss-") and c in KNOWN_CLASSES]
