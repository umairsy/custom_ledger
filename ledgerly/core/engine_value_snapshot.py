# Copyright (c) 2026, Ledgerly Contributors
# License: TBD. See license.txt
"""Value Snapshot engine (user-facing name: "Track changes to a field").

Handles Ledger Configs whose ``ledger_type`` is "Track changes to a field":
tracks one numeric field on one source DocType. Every time the field changes,
an entry is created with the new value, the delta vs the prior value, and a
running balance.

Hooked into every doc save via ``doc_events = {"*": {"on_update": ...}}`` in
``hooks.py``. The first action on every save is a cached lookup that returns
immediately for DocTypes with no Ledger Config — per-save overhead is a single
Redis hit.

Failures inside the engine are logged and swallowed so a misconfigured config
can never break a basic source-doc save.

For ``ledger_type = "Track balance from transactions"`` the engine module will
live alongside this one at ``engine_transactional.py`` (PR #9).
"""

from __future__ import annotations

import frappe
from frappe.utils import flt


_CACHE_PREFIX = "ledgerly:configs_for:"
_EMPTY = "__none__"

# Ledger types this engine handles. Configs with other types are skipped here
# and processed by their respective engines.
# Note: the internal codename "Value Snapshot Ledger" is the historical name;
# the user-facing label is "Track changes to a field". Both are accepted for
# back-compat. Empty string covers legacy un-typed configs from before PR #6.
_HANDLED_TYPES = ("Track changes to a field", "Value Snapshot Ledger", "")


def capture_change(doc, method=None):
    """Main entry point. Called on every doc save and submit."""
    if not _should_capture(doc, method):
        return

    config_names = _get_active_configs_for_doctype(doc.doctype)
    if not config_names:
        return

    for config_name in config_names:
        try:
            _process_config(doc, config_name)
        except Exception:
            frappe.log_error(
                title=f"Ledgerly: failed to process {config_name} for {doc.doctype} {doc.name}",
                message=frappe.get_traceback(),
            )


def invalidate_config_cache(doc, method=None):
    """Clear the cached active-config list when a Ledger Config is saved or deleted."""
    if doc.doctype != "Ledger Config":
        return
    source_doctype = doc.get("source_doctype")
    if source_doctype:
        frappe.cache().delete_value(_CACHE_PREFIX + source_doctype)


def _should_capture(doc, method):
    """Reject hook events that can't usefully produce a Value-Snapshot entry."""
    if doc.doctype in ("Ledger Entry", "Ledger Config", "Ledger Dimension"):
        return False

    if frappe.get_meta(doc.doctype).istable:
        return False

    if method == "on_submit":
        before = doc.get_doc_before_save()
        if before is not None and before.docstatus == 1:
            return False

    return True


def _get_active_configs_for_doctype(source_doctype):
    """Return Value-Snapshot Ledger Config names for this DocType. Cached."""
    cache = frappe.cache()
    cache_key = _CACHE_PREFIX + source_doctype

    cached = cache.get_value(cache_key)
    if cached == _EMPTY:
        return []
    if cached is not None:
        return cached

    try:
        names = frappe.get_all(
            "Ledger Config",
            filters={
                "source_doctype": source_doctype,
                "is_active": 1,
                "ledger_type": ["in", list(_HANDLED_TYPES)],
            },
            pluck="name",
        )
    except Exception:
        # ledger_type column may not exist yet during bench migrate model sync.
        # Fall back to untyped query; do not cache so the next call retries.
        names = frappe.get_all(
            "Ledger Config",
            filters={"source_doctype": source_doctype, "is_active": 1},
            pluck="name",
        )
        return names

    cache.set_value(cache_key, names if names else _EMPTY)
    return names


def _process_config(doc, config_name):
    """Compute new vs old value for one config; create a Ledger Entry if changed."""
    config = frappe.get_cached_doc("Ledger Config", config_name)

    new_value = _compute_value(doc, config)
    old_value = _compute_old_value(doc, config)

    if new_value is None:
        return

    if flt(new_value) == flt(old_value or 0):
        return

    posting_datetime = config.resolve_posting_datetime(doc)
    delta = flt(new_value) - flt(old_value or 0)

    entry = _build_ledger_entry(doc, config, new_value, delta, posting_datetime)

    if _signature_already_exists(config_name, doc.name, entry.change_signature):
        return

    # For "Track changes to a field", balance == value by definition:
    # value stores the current field state, and balance is the canonical
    # running snapshot of that state. Using prior_balance + delta would
    # yield the wrong result whenever a config is newly activated for a
    # document whose field is already non-zero (prior_balance = 0, so
    # balance = delta instead of value).
    entry.balance = flt(new_value)

    if config.narration_field:
        raw = (doc.get(config.narration_field) or "")
        entry.narration = str(raw)[:500] if raw else None

    entry.insert(ignore_permissions=True)
    entry.submit()


def _compute_value(doc, config):
    """Read the tracked value off the source doc."""
    if config.value_source_mode == "Sum across child rows":
        rows = doc.get(config.child_table_field) or []
        return sum(flt(row.get(config.tracked_field) or 0) for row in rows)

    value = doc.get(config.tracked_field)
    return flt(value) if value is not None else None


def _compute_old_value(doc, config):
    """Read the pre-save value of the tracked field. 0 on first insert."""
    before = doc.get_doc_before_save()
    if before is None:
        return 0.0

    if config.value_source_mode == "Sum across child rows":
        rows = before.get(config.child_table_field) or []
        return sum(flt(row.get(config.tracked_field) or 0) for row in rows)

    return flt(before.get(config.tracked_field) or 0)


def _build_ledger_entry(doc, config, value, delta, posting_datetime):
    """Materialise a Ledger Entry Document (not yet inserted)."""
    entry = frappe.new_doc("Ledger Entry")
    entry.ledger_config = config.name
    entry.source_doctype = doc.doctype
    entry.source_name = doc.name
    entry.posting_date = posting_datetime.date()
    entry.posting_time = posting_datetime.time().strftime("%H:%M:%S")
    entry.value = flt(value)
    entry.delta = flt(delta)
    entry.balance = 0

    for idx, dim in enumerate(config.dimensions or [], start=1):
        if idx > 5:
            break
        entry.set(f"dim_{idx}", doc.get(dim.dimension_fieldname))
        entry.set(f"dim_{idx}_doctype", dim.link_doctype)

    entry._compose_posting_datetime()
    entry._compute_change_signature()

    return entry


def _signature_already_exists(config_name, source_name, signature):
    """Check whether a Ledger Entry with this signature already exists."""
    if not signature:
        return False
    return bool(
        frappe.db.exists(
            "Ledger Entry",
            {
                "ledger_config": config_name,
                "source_name": source_name,
                "change_signature": signature,
                "docstatus": 1,
            },
        )
    )


def _compute_current_balance(config_name, source_name, before_datetime):
    """Return running balance for this slice at or before the given datetime.

    NOTE: uses <= (not <) so that same-day entries on Date-only posting fields
    accumulate correctly. See PR #1 for context. Do not change this back to <.
    """
    rows = frappe.get_all(
        "Ledger Entry",
        filters={
            "ledger_config": config_name,
            "source_name": source_name,
            "docstatus": 1,
            "posting_datetime": ["<=", before_datetime],
        },
        fields=["balance"],
        order_by="posting_datetime desc",
        limit=1,
    )
    if not rows:
        return 0.0
    return flt(rows[0].balance)
