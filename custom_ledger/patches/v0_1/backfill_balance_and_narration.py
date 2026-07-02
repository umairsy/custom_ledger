# Copyright (c) 2026, Custom Ledger Contributors
# License: TBD. See license.txt
"""Backfill balance and narration on existing Ledger Entries.

Runs once after the narration field is added to Ledger Entry and the balance
bug (balance = delta instead of value) is fixed in the engine.

Two operations:
1. Balance fix — for "Track changes to a field" configs, balance must equal
   value (the current field snapshot). Any entry where balance != value is
   corrected. This covers entries written before the engine fix landed.

2. Narration backfill — for configs that have a narration_field set, copies
   the current value of that field from the source document into the Ledger
   Entry. Entries that already have a narration are left untouched.

Both operations are idempotent and safe to re-run.
"""

from __future__ import annotations

import frappe
from frappe.utils import flt


_SNAPSHOT_TYPES = ("Track changes to a field", "Value Snapshot Ledger", "")


def execute():
    _fix_balance()
    _backfill_narration()
    frappe.db.commit()


def _fix_balance():
    """Set balance = value for all snapshot-ledger entries where they differ."""
    snapshot_configs = frappe.get_all(
        "Ledger Config",
        filters={"ledger_type": ["in", list(_SNAPSHOT_TYPES)]},
        pluck="name",
    )
    if not snapshot_configs:
        return

    frappe.db.sql(
        """
        UPDATE `tabLedger Entry`
        SET balance = value
        WHERE ledger_config IN %(configs)s
          AND docstatus = 1
          AND ABS(balance - value) > 0.000001
        """,
        {"configs": snapshot_configs},
    )


def _backfill_narration():
    """Copy narration_field value from source docs into Ledger Entries that have none."""
    configs = frappe.get_all(
        "Ledger Config",
        filters={"narration_field": ["!=", ""]},
        fields=["name", "source_doctype", "narration_field"],
    )

    for cfg in configs:
        if not cfg.narration_field:
            continue

        entries = frappe.get_all(
            "Ledger Entry",
            filters={
                "ledger_config": cfg.name,
                "docstatus": 1,
                "narration": ["in", ["", None]],
            },
            fields=["name", "source_name"],
        )
        if not entries:
            continue

        source_names = list({e.source_name for e in entries})
        try:
            source_rows = frappe.get_all(
                cfg.source_doctype,
                filters={"name": ["in", source_names]},
                fields=["name", cfg.narration_field],
            )
        except Exception:
            continue

        narration_map = {r.name: (r.get(cfg.narration_field) or "") for r in source_rows}

        for entry in entries:
            raw = narration_map.get(entry.source_name, "")
            if not raw:
                continue
            narration = str(raw)[:500]
            frappe.db.set_value(
                "Ledger Entry", entry.name, "narration", narration, update_modified=False
            )
