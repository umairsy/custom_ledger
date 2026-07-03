# Copyright (c) 2026, Custom Ledger Contributors
# License: TBD. See license.txt

from __future__ import annotations

import frappe
from frappe import _


@frappe.whitelist()
def get_ledger_views_for_record(doctype: str, name: str) -> list[dict]:
    """Return qualifying Ledger Configs for a specific source record.

    A config qualifies when it is active AND at least one submitted Ledger
    Entry exists for this exact record under that config. Empty list means
    no "View Ledger" button should be rendered.

    Uses frappe.db.exists() (an EXISTS subquery) rather than COUNT so the
    query short-circuits as soon as one matching entry is found.
    """
    if not frappe.has_permission(doctype, "read", name):
        frappe.throw(_("Insufficient permissions to read {0} {1}.").format(doctype, name))

    active_configs = frappe.get_all(
        "Ledger Config",
        filters={"source_doctype": doctype, "is_active": 1},
        fields=["name", "ledger_name"],
        order_by="ledger_name asc",
    )

    result = []
    for cfg in active_configs:
        has_entry = frappe.db.exists(
            "Ledger Entry",
            {
                "ledger_config": cfg["name"],
                "source_name": name,
                "docstatus": 1,
            },
        )
        if has_entry:
            result.append(
                {
                    "config_name": cfg["name"],
                    "config_label": cfg["ledger_name"],
                }
            )

    return result
