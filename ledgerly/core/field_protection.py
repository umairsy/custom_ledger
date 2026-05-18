# Copyright (c) 2026, Ledgerly Contributors
# License: TBD. See license.txt
"""Prevents deletion of Custom Fields referenced by active Ledger Configs.

Registered as a ``before_delete`` hook on the ``Custom Field`` DocType.
Throws a Frappe ValidationError listing the blocking configs so the user
knows exactly why the deletion was rejected.

Checks for references in:
  - ``tracked_field`` (Type 1)
  - ``narration_field`` (Type 1)
  - ``posting_date_field`` (Type 1)
  - ``posting_time_field`` (Type 1)
  - ``balance_field`` on the carrier doctype (Type 2)
  - ``sources`` child table: source_field, carrier_link_field,
    posting_date_field, posting_time_field (Type 2)
  - ``dimensions`` child table: dimension_fieldname (Type 1)
"""

from __future__ import annotations

import frappe
from frappe import _


def block_if_referenced(doc, method=None):
    """Throw if any active Ledger Config references the Custom Field being deleted.

    Args:
        doc: The ``Custom Field`` Document about to be deleted.
    """
    dt = doc.dt          # DocType the custom field belongs to
    fn = doc.fieldname   # fieldname of the custom field

    blocking: list[str] = _find_blocking_configs(dt, fn)
    if not blocking:
        return

    names = ", ".join(blocking)
    frappe.throw(
        _(
            "Cannot delete Custom Field '{0}.{1}': it is referenced by the following "
            "active Ledger Config(s): {2}. Remove or update those configurations first."
        ).format(dt, fn, names)
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _find_blocking_configs(dt: str, fn: str) -> list[str]:
    """Return names of active Ledger Configs that reference DocType.fieldname."""
    blocking: list[str] = []

    # Type 1 — top-level field references on a config whose source_doctype = dt.
    top_level_fields = ("tracked_field", "narration_field", "posting_date_field", "posting_time_field")
    for field in top_level_fields:
        matches = frappe.get_all(
            "Ledger Config",
            filters={
                "source_doctype": dt,
                field: fn,
                "is_active": 1,
            },
            pluck="name",
        )
        blocking.extend(m for m in matches if m not in blocking)

    # Type 1 — dimension_fieldname in the Ledger Dimension child table.
    dim_matches = frappe.db.get_all(
        "Ledger Dimension",
        filters={"dimension_fieldname": fn},
        fields=["parent"],
    )
    for row in dim_matches:
        cfg_name = row["parent"]
        if cfg_name in blocking:
            continue
        # Confirm the parent config is active and has the right source_doctype.
        if frappe.db.get_value(
            "Ledger Config",
            {"name": cfg_name, "source_doctype": dt, "is_active": 1},
            "name",
        ):
            blocking.append(cfg_name)

    # Type 2 — balance_field on a carrier config whose balance_carrier_doctype = dt.
    carrier_matches = frappe.get_all(
        "Ledger Config",
        filters={
            "ledger_type": "Track balance from transactions",
            "balance_carrier_doctype": dt,
            "balance_field": fn,
            "is_active": 1,
        },
        pluck="name",
    )
    blocking.extend(m for m in carrier_matches if m not in blocking)

    # Type 2 — source row fields in the Ledger Source child table.
    source_row_fields = ("source_field", "carrier_link_field", "posting_date_field", "posting_time_field")
    for field in source_row_fields:
        src_matches = frappe.db.get_all(
            "Ledger Source",
            filters={"source_doctype": dt, field: fn},
            fields=["parent"],
        )
        for row in src_matches:
            cfg_name = row["parent"]
            if cfg_name in blocking:
                continue
            if frappe.db.get_value("Ledger Config", {"name": cfg_name, "is_active": 1}, "name"):
                blocking.append(cfg_name)

    return blocking
