"""Single source of truth for how a tree status is shown (UI doc §7).

Colour alone is never enough — every status carries an icon and a label as well, so the
same three pieces are used by the template tag, the map popups (via json_script) and,
later, the notification e-mails. Icons come from the PoC (poc/assets/app.js).
"""

from django.utils.safestring import mark_safe

from .models import Tree

_CHECK = """<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor"
 stroke-width="3" stroke-linecap="round" stroke-linejoin="round">
 <path d="M20 6L9 17l-5-5"/></svg>"""
_DROP = """<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2C8 8 5
 11.5 5 15a7 7 0 0 0 14 0c0-3.5-3-7-7-13z" opacity=".35"/><path d="M12 2C8 8 5 11.5 5 15a7 7 0 0 0 7
 7V2z"/></svg>"""
_ALERT = """<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2L1
 21h22L12 2z"/><rect x="11" y="9" width="2" height="6" fill="#fff"/><rect x="11" y="17" width="2"
 height="2" fill="#fff"/></svg>"""

STATUS_DISPLAY = {
    Tree.Status.OK: {
        "label": "Podlane",
        "hint": "Niedawno podlane lub padał deszcz",
        "icon": mark_safe(_CHECK),  # noqa: S308 — constant markup, no user input
    },
    Tree.Status.SOON: {
        "label": "Wkrótce podlać",
        "hint": "Zbliża się potrzeba podlania",
        "icon": mark_safe(_DROP),  # noqa: S308
    },
    Tree.Status.URGENT: {
        "label": "Pilnie podlać!",
        "hint": "Susza — drzewo czeka na wodę",
        "icon": mark_safe(_ALERT),  # noqa: S308
    },
}


def status_labels():
    """Plain (JSON-serialisable) labels for the map script."""
    return {status: {"label": data["label"]} for status, data in STATUS_DISPLAY.items()}
