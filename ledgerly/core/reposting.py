# Copyright (c) 2026, Ledgerly Contributors
# License: TBD. See license.txt
"""Ledger reposting and integrity checks.

Back-dated entries only corrupt one thing, and only for one ledger type:

- **Type 2 (transactional)** stores no per-entry running balance — the report
  derives it by ordering deltas, and the carrier field is ``SUM(delta)`` (order
  independent). So a back-dated entry needs no repost; at most the carrier field
  is refreshed.
- **Type 1 (value snapshot)** stores an absolute ``balance`` snapshot plus a
  ``delta`` vs the previous reading. A back-dated reading breaks the *delta
  chain*: its own delta and the next reading's delta are computed against the
  wrong predecessor. Reposting recomputes ``delta[i] = balance[i] - balance[i-1]``
  in posting order for the affected source slice.

Reposting is scoped to a single slice and runs in a background job. Immutable
ledgers never reach here — they block back-dating at entry time.
"""

from __future__ import annotations

import frappe
from frappe.utils import flt

TRANSACTIONAL_TYPE = "Track balance from transactions"


# ---------------------------------------------------------------------------
# Enqueue + worker (Type 1 delta chain)
# ---------------------------------------------------------------------------

def enqueue_slice_repost(ledger_config: str, source_name: str) -> None:
    """Queue a background delta-chain repost for one value-snapshot source slice.

    Deduplicated: a slice already queued won't pile up duplicate jobs.
    """
    frappe.enqueue(
        "ledgerly.core.reposting.repost_value_snapshot_slice",
        queue="short",
        job_id=f"ledgerly-repost::{ledger_config}::{source_name}",
        deduplicate=True,
        ledger_config=ledger_config,
        source_name=source_name,
    )


def repost_value_snapshot_slice(ledger_config: str, source_name: str) -> int:
    """Recompute the delta chain for one value-snapshot slice.

    ``balance`` stays the stored absolute snapshot; only ``delta`` is corrected,
    and only rows whose delta actually changed are written. Returns the number
    of rows corrected.
    """
    entries = frappe.get_all(
        "Ledger Entry",
        filters={"ledger_config": ledger_config, "source_name": source_name, "docstatus": 1},
        fields=["name", "balance", "delta"],
        order_by="posting_datetime asc, name asc",
    )
    prev = 0.0
    corrected = 0
    for entry in entries:
        expected = flt(entry.balance) - prev
        if flt(entry.delta) != expected:
            frappe.db.set_value("Ledger Entry", entry.name, "delta", expected, update_modified=False)
            corrected += 1
        prev = flt(entry.balance)
    return corrected


# ---------------------------------------------------------------------------
# Manual repost (whitelisted — "Repost Ledger" button)
# ---------------------------------------------------------------------------

@frappe.whitelist()
def repost_ledger(ledger_config: str) -> dict:
    """Repost an entire ledger on demand. Type 1 enqueues one job per source
    slice; Type 2 refreshes each carrier's balance field (already order-safe)."""
    frappe.has_permission("Ledger Config", "write", ledger_config, throw=True)
    config = frappe.get_cached_doc("Ledger Config", ledger_config)

    if config.ledger_type == TRANSACTIONAL_TYPE:
        carriers = _refresh_transactional_carriers(config)
        return {"ledger_type": config.ledger_type, "refreshed_carriers": carriers}

    slices = _distinct_sources(ledger_config)
    for source_name in slices:
        enqueue_slice_repost(ledger_config, source_name)
    return {"ledger_type": config.ledger_type, "queued_slices": len(slices)}


def _refresh_transactional_carriers(config) -> int:
    from ledgerly.core.engine_transactional import _write_carrier_balance

    carriers = frappe.get_all(
        "Ledger Entry",
        filters={"ledger_config": config.name, "docstatus": 1},
        fields=["carrier_doctype", "carrier_name"],
        distinct=True,
    )
    for carrier in carriers:
        _write_carrier_balance(
            carrier_doctype=carrier.carrier_doctype,
            carrier_name=carrier.carrier_name,
            balance_field=config.balance_field,
            ledger_config=config.name,
        )
    return len(carriers)


# ---------------------------------------------------------------------------
# Integrity check (whitelisted — "Check Ledger Integrity" button)
# ---------------------------------------------------------------------------

@frappe.whitelist()
def check_ledger_integrity(ledger_config: str) -> dict:
    """Scan a ledger for running-balance anomalies. Read-only; returns issues."""
    frappe.has_permission("Ledger Config", "read", ledger_config, throw=True)
    config = frappe.get_cached_doc("Ledger Config", ledger_config)

    if config.ledger_type == TRANSACTIONAL_TYPE:
        anomalies = _check_transactional(config)
    else:
        anomalies = _check_value_snapshot(config)

    return {
        "ledger_type": config.ledger_type,
        "anomaly_count": len(anomalies),
        "anomalies": anomalies[:200],
    }


def _check_value_snapshot(config) -> list[dict]:
    """Delta-chain anomalies: stored delta != balance - previous balance."""
    issues: list[dict] = []
    for source_name in _distinct_sources(config.name):
        entries = frappe.get_all(
            "Ledger Entry",
            filters={"ledger_config": config.name, "source_name": source_name, "docstatus": 1},
            fields=["name", "balance", "delta"],
            order_by="posting_datetime asc, name asc",
        )
        prev = 0.0
        for entry in entries:
            expected = flt(entry.balance) - prev
            if flt(entry.delta) != expected:
                issues.append(
                    {
                        "slice": source_name,
                        "entry": entry.name,
                        "stored_delta": flt(entry.delta),
                        "expected_delta": expected,
                    }
                )
            prev = flt(entry.balance)
    return issues


def _check_transactional(config) -> list[dict]:
    """Carrier-field anomalies: carrier balance field != SUM(delta)."""
    issues: list[dict] = []
    carriers = frappe.get_all(
        "Ledger Entry",
        filters={"ledger_config": config.name, "docstatus": 1},
        fields=["carrier_doctype", "carrier_name"],
        distinct=True,
    )
    for carrier in carriers:
        total = frappe.db.sql(
            """
            SELECT COALESCE(SUM(delta), 0)
            FROM `tabLedger Entry`
            WHERE ledger_config = %s AND carrier_doctype = %s
              AND carrier_name = %s AND docstatus = 1
            """,
            (config.name, carrier.carrier_doctype, carrier.carrier_name),
        )[0][0]
        field_value = frappe.db.get_value(carrier.carrier_doctype, carrier.carrier_name, config.balance_field)
        if flt(field_value) != flt(total):
            issues.append(
                {
                    "carrier": f"{carrier.carrier_doctype} {carrier.carrier_name}",
                    "carrier_field": flt(field_value),
                    "expected": flt(total),
                }
            )
    return issues


def _distinct_sources(ledger_config: str) -> list[str]:
    return frappe.get_all(
        "Ledger Entry",
        filters={"ledger_config": ledger_config, "docstatus": 1},
        pluck="source_name",
        distinct=True,
    )
