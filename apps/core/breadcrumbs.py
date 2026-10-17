"""Breadcrumbs for every page (v0.9.2): built from the URL, with page templates able to override the last crumb.

``Home › Open data › Monitoring sites``. Labels for known URL segments come
from :data:`LABELS`; anything else (a reference number, a slug) is shown as
is, title-cased for slugs. Templates set ``{% block crumb_title %}`` to replace
the last crumb with something better (an application reference, a dataset
title), and views may pass ``breadcrumbs`` explicitly.
"""
from __future__ import annotations

LABELS = {
    "licensing": "Licensing", "applications": "Applications", "new": "New application", "licences": "Licences", "balance": "WMU balance", "assessment": "Technical assessment",
    "submissions": "Data submissions", "csv": "CSV upload", "form": "Form", "workflow": "Review queue", "queue": None, "maps": "Map", "full": "Full screen",
    "export": "GIS package", "wmu-balance": "WMU balance",
    "layers": "Layers", "open-data": "Open data", "documents": "Publications", "unit": "My unit", "issues": "Cleansing queue", "members": "People", "adoption": "Adoption",
    "dashboards": "Dashboards", "wall": "Wall display", "exports": "Exports", "finance": "Finance export", "accounts": "Account", "profile": "Profile", "login": "Sign in",
    "register": "Register", "mfa": "Two-factor sign-in", "setup": "Set up", "verify": "Verify", "backup-codes": "Backup codes", "reset": "Reset", "privacy": "Privacy notice",
    "notifications": "Notifications", "executive": "Executive view", "milestones": "Milestones", "api": "API", "docs": "Documentation", "admin": "Admin console",
}
#: segments that have no page of their own: shown as text, not linked
UNLINKED = {"licensing", "exports", "accounts", "api", "layers", "issues", "members", "documents"}


def _label(segment: str) -> str | None:
    if segment in LABELS:
        return LABELS[segment]
    if segment.isdigit() or segment.upper() == segment:
        return segment  # an id or a reference number
    return segment.replace("-", " ").replace("_", " ").capitalize()


def build(path: str) -> list[dict]:
    """Crumbs for ``path``: list of {label, url, last}; empty on the home page."""
    parts = [p for p in path.split("/") if p]
    if not parts or parts[0] in ("admin", "static", "media"):
        return []
    crumbs = [{"label": "Home", "url": "/", "last": False}]
    acc = ""
    for i, seg in enumerate(parts):
        acc += f"/{seg}"
        label = _label(seg)
        if label is None:
            continue
        last = i == len(parts) - 1
        crumbs.append({"label": label, "url": None if (seg in UNLINKED or last) else acc + "/", "last": last})
    crumbs[-1]["last"] = True
    return crumbs
