# Copyright (c) 2026, Ledgerly Contributors
# License: TBD. See license.txt
"""Backfill ``ledger_type`` on existing Ledger Configs.

Runs once after PR #6 introduces the ``ledger_type`` field. For every existing
config that has no type set, defaults to 'Track changes to a field' — the only
behaviour Ledgerly had before this field existed.

Idempotent: safe to run again on configs that already have a type set.
"""

import frappe


def execute():
    frappe.db.sql(
        """
        UPDATE `tabLedger Config`
        SET ledger_type = 'Track changes to a field'
        WHERE ledger_type IS NULL OR ledger_type = ''
        """
    )
    frappe.db.commit()
