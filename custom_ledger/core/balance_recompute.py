# Copyright (c) 2026, Custom Ledger Contributors
# License: TBD. See license.txt
"""Self-healing balance recompute for Type 2 ('Track balance from transactions') ledgers.

Called via the ``on_load`` doc event hook for every document. Fast-exits in
O(1) for any DocType that is not a carrier for an active Type 2 Ledger Config.

When drift is detected (carrier balance_field ≠ sum of Ledger Entry deltas for
that carrier), the balance field is silently corrected without bumping modified.

Recompute is skipped:
  - During engine writes (``frappe.flags.custom_ledger_engine_writing``) — prevents
    recursion when the engine itself loads the carrier doc.
  - Outside web requests (background jobs, bench console) — healing is a UX
    aid for interactive form opens, not a background job.
"""

from __future__ import annotations

import frappe
from frappe.utils import flt


def recompute_on_load(doc, method=None):
    """Entry point — registered as the ``on_load`` hook on ``"*"``."""
    if frappe.flags.get("custom_ledger_engine_writing"):
        return

    # Only heal during interactive web requests.
    if not getattr(frappe.local, "request", None):
        return

    configs = _get_type_2_configs_for_carrier(doc.doctype)
    if not configs:
        return

    for cfg in configs:
        _heal_balance(doc, cfg["name"], cfg["balance_field"])


def _get_type_2_configs_for_carrier(carrier_doctype: str) -> list[dict]:
    """Return active Type 2 configs whose balance_carrier_doctype = carrier_doctype.

    Result is not cached deliberately: the Ledger Config list can change without
    a cache invalidation signal tied to the carrier doctype, and the query is
    narrow (uses a composite index on ledger_type + balance_carrier_doctype).
    """
    return frappe.get_all(
        "Ledger Config",
        filters={
            "ledger_type": "Track balance from transactions",
            "balance_carrier_doctype": carrier_doctype,
            "is_active": 1,
        },
        fields=["name", "balance_field"],
    )


def _heal_balance(doc, config_name: str, balance_field: str) -> None:
    """Recompute the carrier's balance from Ledger Entry deltas; correct on drift.

    Only heals when at least one Ledger Entry exists for this config and carrier
    — if no entries exist yet we cannot distinguish 'truly zero' from 'not yet
    tracked', so we leave the field untouched.
    """
    config = frappe.get_cached_doc("Ledger Config", config_name)

    total = 0.0
    found_any_entry = False

    for source in config.sources or []:
        if not source.is_active:
            continue

        # Find submitted source docs whose carrier link points to this carrier doc.
        try:
            source_names = frappe.get_all(
                source.source_doctype,
                filters={source.carrier_link_field: doc.name, "docstatus": 1},
                pluck="name",
            )
        except Exception:
            continue

        if not source_names:
            continue

        entries = frappe.get_all(
            "Ledger Entry",
            filters={
                "ledger_config": config_name,
                "source_doctype": source.source_doctype,
                "source_name": ["in", source_names],
                "docstatus": 1,
            },
            fields=["delta"],
        )

        if entries:
            found_any_entry = True
            total += sum(flt(e["delta"]) for e in entries)

    if not found_any_entry:
        return

    current = flt(doc.get(balance_field))
    if abs(current - total) <= 1e-6:
        return

    frappe.db.set_value(doc.doctype, doc.name, balance_field, total, update_modified=False)
    doc.set(balance_field, total)
