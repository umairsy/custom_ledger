# Copyright (c) 2026, Custom Ledger Contributors
# License: TBD. See license.txt
"""ERPNext integration — thin, optional.

ERPNext is an optional dependency: Custom Ledger must install and run without
it. This module never imports erpnext at module load; it only reports whether
erpnext is installed so the Ledger Entry form can conditionally offer a
"Create → Journal Entry / Stock Entry / Stock Reconciliation" action.

The actual transaction is built client-side (pre-filled + opened for the user
to complete), so no ERPNext-specific server logic lives here.
"""

from __future__ import annotations

import frappe


@frappe.whitelist()
def is_erpnext_installed() -> bool:
    """True iff erpnext is installed on the current site."""
    return "erpnext" in frappe.get_installed_apps()
