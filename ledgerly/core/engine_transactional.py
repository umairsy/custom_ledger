# Copyright (c) 2026, Ledgerly Contributors
# License: TBD. See license.txt
"""Transactional engine for Type 2 Ledger Configs ("Track balance from transactions").

Hooks into every doc's ``on_submit`` and ``on_cancel`` events via the wildcard
``"*"`` registration in ``hooks.py``. First action on every save is a cached
lookup that returns immediately for DocTypes that are not feeders of any
active Type 2 config — so the per-save overhead is a single Redis hit.

Failures inside the engine are logged and swallowed so a misconfigured config
can never block a feeder save.

This engine is independent of ``engine_value_snapshot`` (the Type 1 engine).
They share no code paths; each filters internally for the ledger types it
handles.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import flt, get_datetime

from ledgerly.core.exceptions import NegativeBalanceError


_FEEDER_CACHE_KEY = "ledgerly:type2_feeders"
_EMPTY = "__none__"


# ---------------------------------------------------------------------------
# Public hook entry points
# ---------------------------------------------------------------------------

def capture_submit(doc, method=None):
    """Hook entry point for ``on_submit``."""
    if not _is_feeder_doctype(doc.doctype):
        return

    try:
        _process_submit(doc)
    except NegativeBalanceError:
        # Deliberate block — must propagate to stop the feeder submit.
        raise
    except Exception:
        frappe.log_error(
            title=f"Ledgerly transactional engine: submit failed for {doc.doctype} {doc.name}",
            message=frappe.get_traceback(),
        )


def capture_cancel(doc, method=None):
    """Hook entry point for ``on_cancel`` — reverse previously-created entries."""
    if not _is_feeder_doctype(doc.doctype):
        return

    try:
        _process_cancel(doc)
    except Exception:
        frappe.log_error(
            title=f"Ledgerly transactional engine: cancel failed for {doc.doctype} {doc.name}",
            message=frappe.get_traceback(),
        )


def invalidate_feeder_cache(doc=None, method=None):
    """Clear the cached feeder-doctype set. Called from Ledger Config events and after_migrate."""
    frappe.cache().delete_value(_FEEDER_CACHE_KEY)


# ---------------------------------------------------------------------------
# Feeder doctype cache
# ---------------------------------------------------------------------------

def _is_feeder_doctype(doctype: str) -> bool:
    """Return True iff this doctype is referenced as a source in any active Type 2 config."""
    return doctype in _get_feeder_doctypes()


def _get_feeder_doctypes() -> set[str]:
    """Cached set of doctypes that appear as a source in any active Type 2 config."""
    cache = frappe.cache()
    cached = cache.get_value(_FEEDER_CACHE_KEY)
    if cached == _EMPTY:
        return set()
    if cached:
        return set(cached)

    rows = frappe.db.sql(
        """
        SELECT DISTINCT ls.source_doctype
        FROM `tabLedger Source` ls
        INNER JOIN `tabLedger Config` lc ON lc.name = ls.parent
        WHERE lc.is_active = 1
          AND lc.ledger_type = 'Track balance from transactions'
          AND ls.is_active = 1
        """,
        as_dict=False,
    )
    feeders = {r[0] for r in rows if r[0]}

    cache.set_value(_FEEDER_CACHE_KEY, list(feeders) if feeders else _EMPTY)
    return feeders


# ---------------------------------------------------------------------------
# Submit path
# ---------------------------------------------------------------------------

def _process_submit(doc) -> None:
    """For each active Type 2 source matching doc.doctype, create a Ledger Entry."""
    sources = _matching_sources(doc.doctype)
    if not sources:
        return

    for source in sources:
        if source["child_table_field"]:
            frappe.log_error(
                title="Ledgerly: skipping child-table source (not yet supported)",
                message=(
                    f"Source on Ledger Config '{source['ledger_config']}' uses "
                    f"child_table_field='{source['child_table_field']}'. "
                    "Child-table sources are not yet supported by the transactional engine."
                ),
            )
            continue

        _create_entry_for_source(doc, source)


def _matching_sources(doctype: str) -> list[dict]:
    """Return all active Ledger Source rows matching ``doctype`` on active Type 2 configs."""
    return frappe.db.sql(
        """
        SELECT
            lc.name          AS ledger_config,
            lc.ledger_name,
            lc.balance_carrier_doctype,
            lc.balance_field,
            lc.allow_negative_balance,
            ls.source_field,
            ls.child_table_field,
            ls.direction,
            ls.carrier_link_field,
            ls.posting_date_field,
            ls.posting_time_field
        FROM `tabLedger Source` ls
        INNER JOIN `tabLedger Config` lc ON lc.name = ls.parent
        WHERE lc.is_active = 1
          AND lc.ledger_type = 'Track balance from transactions'
          AND ls.is_active = 1
          AND ls.source_doctype = %s
        """,
        (doctype,),
        as_dict=True,
    )


def _create_entry_for_source(doc, source: dict) -> None:
    """Compute, validate, and insert a single Ledger Entry; then update carrier balance."""
    raw_value = doc.get(source["source_field"])
    if raw_value is None:
        return

    value = flt(raw_value)
    if value == 0:
        return

    delta = value if source["direction"] == "ADD" else -value

    carrier_name = doc.get(source["carrier_link_field"])
    if not carrier_name:
        frappe.log_error(
            title="Ledgerly: missing carrier link value",
            message=(
                f"Doc {doc.doctype} {doc.name} has no value in carrier_link_field "
                f"'{source['carrier_link_field']}'. Cannot scope the ledger entry."
            ),
        )
        return

    if _entry_already_exists(source["ledger_config"], doc.doctype, doc.name, source["source_field"]):
        return

    # Negative-balance guard. Block the feeder submit if this delta would take
    # the carrier's running balance below zero, unless the config opted in.
    if not source["allow_negative_balance"]:
        current = _carrier_current_balance(
            source["ledger_config"], source["balance_carrier_doctype"], carrier_name
        )
        proposed = current + delta
        if proposed < 0:
            frappe.throw(
                _(
                    "This {0} would take {1} '{2}' to a balance of {3}, but negative "
                    "balances are not allowed for ledger '{4}'. Enable 'Allow Negative "
                    "Balance' on the Ledger Config to permit this."
                ).format(
                    doc.doctype,
                    source["balance_carrier_doctype"],
                    carrier_name,
                    flt(proposed),
                    source["ledger_name"],
                ),
                exc=NegativeBalanceError,
                title=_("Negative Balance Not Allowed"),
            )

    posting_dt = _resolve_posting_datetime(doc, source)

    entry = frappe.new_doc("Ledger Entry")
    entry.ledger_config = source["ledger_config"]
    entry.source_doctype = doc.doctype
    entry.source_name = doc.name
    entry.source_field = source["source_field"]
    entry.carrier_doctype = source["balance_carrier_doctype"]
    entry.carrier_name = carrier_name
    entry.value = value
    entry.delta = delta
    entry.balance = 0  # computed by _write_carrier_balance; set to 0 for now
    entry.posting_date = posting_dt.date()
    entry.posting_time = str(posting_dt.time())
    entry.posting_datetime = posting_dt

    entry.insert(ignore_permissions=True)
    entry.submit()

    _write_carrier_balance(
        carrier_doctype=source["balance_carrier_doctype"],
        carrier_name=carrier_name,
        balance_field=source["balance_field"],
        ledger_config=source["ledger_config"],
    )


# ---------------------------------------------------------------------------
# Cancel path
# ---------------------------------------------------------------------------

def _process_cancel(doc) -> None:
    """For each entry previously created for this feeder doc, create an opposite-signed reversal."""
    existing_entries = frappe.get_all(
        "Ledger Entry",
        filters={
            "source_doctype": doc.doctype,
            "source_name": doc.name,
            "docstatus": 1,
            "is_reversal": 0,
        },
        fields=[
            "name",
            "ledger_config",
            "carrier_doctype",
            "carrier_name",
            "source_field",
            "value",
            "delta",
            "posting_date",
            "posting_time",
            "posting_datetime",
        ],
    )

    for orig in existing_entries:
        if _reversal_already_exists(orig["name"]):
            continue

        reversal = frappe.new_doc("Ledger Entry")
        reversal.ledger_config = orig["ledger_config"]
        reversal.source_doctype = doc.doctype
        reversal.source_name = doc.name
        reversal.source_field = orig["source_field"]
        reversal.carrier_doctype = orig["carrier_doctype"]
        reversal.carrier_name = orig["carrier_name"]
        reversal.value = orig["value"]
        reversal.delta = -flt(orig["delta"])
        reversal.balance = 0
        reversal.posting_date = orig["posting_date"]
        reversal.posting_time = orig["posting_time"]
        reversal.posting_datetime = orig["posting_datetime"]
        reversal.is_reversal = 1
        reversal.reverses = orig["name"]

        reversal.insert(ignore_permissions=True)
        reversal.submit()

        _write_carrier_balance(
            carrier_doctype=orig["carrier_doctype"],
            carrier_name=orig["carrier_name"],
            balance_field=_get_balance_field(orig["ledger_config"]),
            ledger_config=orig["ledger_config"],
        )


def _get_balance_field(ledger_config: str) -> str:
    """Return the balance_field for a given Ledger Config."""
    return frappe.db.get_value("Ledger Config", ledger_config, "balance_field") or ""


# ---------------------------------------------------------------------------
# Carrier balance write (Commit 3)
# ---------------------------------------------------------------------------

def _write_carrier_balance(
    *, carrier_doctype: str, carrier_name: str, balance_field: str, ledger_config: str
) -> None:
    """Recompute and persist the carrier's balance after an engine write.

    Uses the engine bypass flag so the recompute-on-load hook doesn't see this
    as drift, and so any future before_save protections allow the write.
    """
    if not balance_field:
        return

    row = frappe.db.sql(
        """
        SELECT COALESCE(SUM(delta), 0)
        FROM `tabLedger Entry`
        WHERE ledger_config = %s
          AND carrier_doctype = %s
          AND carrier_name = %s
          AND docstatus = 1
        """,
        (ledger_config, carrier_doctype, carrier_name),
    )
    total = flt(row[0][0]) if row else 0.0

    frappe.flags.ledgerly_engine_writing = True
    try:
        frappe.db.set_value(
            carrier_doctype, carrier_name, balance_field, total, update_modified=False
        )
    finally:
        frappe.flags.ledgerly_engine_writing = False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _carrier_current_balance(ledger_config: str, carrier_doctype: str, carrier_name: str) -> float:
    """Current running balance for a carrier = sum of submitted entry deltas.

    Computed from the entries (the source of truth), not the carrier doc field,
    so the guard is correct even if the carrier field drifted.
    """
    row = frappe.db.sql(
        """
        SELECT COALESCE(SUM(delta), 0)
        FROM `tabLedger Entry`
        WHERE ledger_config = %s
          AND carrier_doctype = %s
          AND carrier_name = %s
          AND docstatus = 1
        """,
        (ledger_config, carrier_doctype, carrier_name),
    )
    return flt(row[0][0]) if row else 0.0


def _entry_already_exists(
    ledger_config: str, source_doctype: str, source_name: str, source_field: str
) -> bool:
    """Idempotency check — don't double-post for the same source/field."""
    return bool(
        frappe.db.exists(
            "Ledger Entry",
            {
                "ledger_config": ledger_config,
                "source_doctype": source_doctype,
                "source_name": source_name,
                "source_field": source_field,
                "docstatus": 1,
                "is_reversal": 0,
            },
        )
    )


def _reversal_already_exists(original_entry_name: str) -> bool:
    """Idempotency check for cancel."""
    return bool(
        frappe.db.exists(
            "Ledger Entry",
            {"reverses": original_entry_name, "is_reversal": 1, "docstatus": 1},
        )
    )


def _resolve_posting_datetime(doc, source: dict):
    """Combine date and (optional) time fields into a datetime."""
    date_value = doc.get(source["posting_date_field"])
    if not date_value:
        frappe.throw(
            f"Source field '{source['posting_date_field']}' on {doc.doctype} {doc.name} is blank. "
            f"Required for Ledger Config '{source['ledger_config']}'."
        )

    if source["posting_time_field"]:
        time_value = doc.get(source["posting_time_field"])
        if time_value:
            return get_datetime(f"{date_value} {time_value}")

    return get_datetime(date_value)
