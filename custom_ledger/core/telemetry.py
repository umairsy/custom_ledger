# Copyright (c) 2026, Custom Ledger Contributors
# License: GNU General Public License v3. See license.txt
"""Opt-in, anonymous usage telemetry.

DISABLED BY DEFAULT. Nothing is ever sent unless a site admin explicitly opts in
by setting two site-config keys:

    bench --site <site> set-config custom_ledger_telemetry 1
    bench --site <site> set-config custom_ledger_telemetry_url "https://<your-endpoint>"

When enabled, a weekly scheduled job POSTs a small, anonymous JSON payload to
that URL:

    - site:           an opaque one-way hash of the site name (not reversible,
                      used only to count distinct installs)
    - app_version:    Custom Ledger version
    - frappe_version: Frappe version
    - ledger_configs / active_ledger_configs / ledger_entries: plain counts

It NEVER sends the site name or URL, user identities, or any ledger contents.
Any error is swallowed so telemetry can never affect the site. To turn it off,
set ``custom_ledger_telemetry`` to 0 (or remove the keys).
"""

from __future__ import annotations

import hashlib

import frappe

TELEMETRY_FLAG = "custom_ledger_telemetry"
TELEMETRY_URL = "custom_ledger_telemetry_url"


def send_telemetry() -> None:
    """Weekly scheduled job. No-op unless the site opted in and set a URL."""
    if not frappe.conf.get(TELEMETRY_FLAG):
        return
    url = frappe.conf.get(TELEMETRY_URL)
    if not url:
        return
    try:
        import requests  # bundled with Frappe

        requests.post(url, json=_build_payload(), timeout=5)
    except Exception:
        # Telemetry must never break a site; stay silent on any failure.
        pass


def _site_hash() -> str:
    """Opaque, stable identifier for this install — a one-way hash of the site
    name. It counts distinct installs without revealing which site they are."""
    raw = (frappe.local.site or "").encode()
    return hashlib.sha256(raw).hexdigest()[:16]


def _build_payload() -> dict:
    import custom_ledger

    return {
        "site": _site_hash(),
        "app_version": getattr(custom_ledger, "__version__", None),
        "frappe_version": frappe.__version__,
        "ledger_configs": frappe.db.count("Ledger Config"),
        "active_ledger_configs": frappe.db.count("Ledger Config", {"is_active": 1}),
        "ledger_entries": frappe.db.count("Ledger Entry"),
    }
