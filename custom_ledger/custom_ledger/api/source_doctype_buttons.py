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

    T2 = "Track balance from transactions"
    result: list[dict] = []

    def _add(cfg_name, label, scope, filter_field, rec):
        if frappe.db.exists("Ledger Entry", {"ledger_config": cfg_name, filter_field: rec, "docstatus": 1}):
            result.append({"config_name": cfg_name, "config_label": label, "scope": scope})

    # Type 1 source: this record IS the tracked document → its own ledger.
    for cfg in frappe.get_all(
        "Ledger Config", filters={"source_doctype": doctype, "is_active": 1, "ledger_type": ["!=", T2]},
        fields=["name", "ledger_name"], order_by="ledger_name asc",
    ):
        _add(cfg["name"], cfg["ledger_name"], "source", "source_name", name)

    # Type 2 feeder: this record is a transaction → the ledger for THIS transaction only.
    for cfg in frappe.db.sql(
        """SELECT DISTINCT lc.name, lc.ledger_name FROM `tabLedger Source` ls
           JOIN `tabLedger Config` lc ON lc.name = ls.parent
           WHERE ls.source_doctype=%s AND ls.is_active=1 AND lc.is_active=1 AND lc.ledger_type=%s
           ORDER BY lc.ledger_name""", (doctype, T2), as_dict=True,
    ):
        _add(cfg["name"], cfg["ledger_name"], "source", "source_name", name)

    # Type 2 carrier: this record is the carrier → its COMPLETE running ledger.
    for cfg in frappe.get_all(
        "Ledger Config", filters={"balance_carrier_doctype": doctype, "is_active": 1, "ledger_type": T2},
        fields=["name", "ledger_name"], order_by="ledger_name asc",
    ):
        _add(cfg["name"], cfg["ledger_name"], "carrier", "carrier_name", name)

    return result
