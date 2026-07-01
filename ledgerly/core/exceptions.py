# Copyright (c) 2026, Ledgerly Contributors
# License: TBD. See license.txt
"""Ledgerly engine exceptions.

A dedicated exception so the engines can deliberately *block* a source-doc
save (e.g. a negative-balance violation) while still swallowing every other,
incidental failure. The engine entry points catch this type and re-raise it,
but log-and-swallow anything else.
"""

from __future__ import annotations

import frappe


class NegativeBalanceError(frappe.ValidationError):
    """Raised when an entry would drive a ledger balance below zero and the
    Ledger Config has not opted in via ``allow_negative_balance``."""


class BackdatedEntryError(frappe.ValidationError):
    """Raised when an entry is posted before the latest entry in its slice and
    the Ledger Config is Immutable (does not permit back-dating / reposting)."""
