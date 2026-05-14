# Copyright (c) 2026, Ledgerly Contributors
# License: TBD. See license.txt
"""Custom Ledger report.

A Frappe Script Report that renders a Ledger Config's entries as a ledger:
posting date, value, delta, running balance, plus the dimensions configured
on the Ledger Config.

Filter semantics:
- ledger_config (mandatory): selects which Ledger Config's entries to show
  AND which columns to render.
- from_date / to_date: window over posting_date (inclusive on both ends).
- source_name: narrow to a single source document.
- group_by_source: when True, sources are grouped. Each source gets an
  Opening Balance row, its entries, and a Closing Balance row.
- dim_1 ... dim_5: one filter per configured dimension on the Ledger Config.

Cancelled entries (docstatus=2) are always excluded.

Opening Balance semantics:
- Per source: the balance of the last entry with posting_datetime < from_date.
- Falls back to 0 if no prior entry exists.
- Dimension filters do NOT affect opening balance computation. Balance is
  per-source; dimensions are visual slicers within the window.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import flt, getdate

# Fieldname constants — used throughout to keep call sites readable.
FN_POSTING_DATE = "posting_date"
FN_POSTING_TIME = "posting_time"
FN_POSTING_DATETIME = "posting_datetime"
FN_SOURCE_DOCTYPE = "source_doctype"
FN_SOURCE_NAME = "source_name"
FN_VALUE = "value"
FN_DELTA = "delta"
FN_BALANCE = "balance"

# Maximum dimension columns supported by Ledger Entry. Kept in sync with the
# DocType schema. If the schema ever grows, bump this and the indexed dim_N
# usage below.
MAX_DIMENSIONS = 5


def execute(filters: dict | None = None):
    """Main entry point. Frappe calls this with the report's filter values."""
    filters = filters or {}

    if not filters.get("ledger_config"):
        # Mandatory filter not supplied — return empty result with a helpful
        # column hint rather than raising.
        return [], []

    config = frappe.get_cached_doc("Ledger Config", filters["ledger_config"])

    _validate_filters(filters)

    columns = _build_columns(config)
    data = _build_data(config, filters)

    return columns, data


# ----------------------------------------------------------------------
# Filter validation
# ----------------------------------------------------------------------

def _validate_filters(filters: dict) -> None:
    """Raise on filter combinations that don't make sense."""
    from_date = filters.get("from_date")
    to_date = filters.get("to_date")
    if from_date and to_date and getdate(to_date) < getdate(from_date):
        frappe.throw(_("To Date cannot be earlier than From Date."))


# ----------------------------------------------------------------------
# Column construction
# ----------------------------------------------------------------------

def _build_columns(config) -> list[dict]:
    """Return Frappe Script Report column defs for this Ledger Config.

    Always returns the base columns (date/time/source/value/delta/balance),
    plus one column per dimension declared on the Ledger Config. Dimension
    columns are Dynamic Link pointing at the dimension's link_doctype.
    """
    columns: list[dict] = [
        {
            "fieldname": FN_POSTING_DATE,
            "label": _("Posting Date"),
            "fieldtype": "Date",
            "width": 110,
        },
        {
            "fieldname": FN_POSTING_TIME,
            "label": _("Time"),
            "fieldtype": "Time",
            "width": 90,
        },
        {
            "fieldname": FN_SOURCE_NAME,
            "label": _("Source Document"),
            "fieldtype": "Dynamic Link",
            "options": FN_SOURCE_DOCTYPE,
            "width": 180,
        },
        {
            "fieldname": FN_VALUE,
            "label": _("Value"),
            "fieldtype": "Float",
            "precision": 6,
            "width": 110,
        },
        {
            "fieldname": FN_DELTA,
            "label": _("Delta"),
            "fieldtype": "Float",
            "precision": 6,
            "width": 110,
        },
        {
            "fieldname": FN_BALANCE,
            "label": _("Balance"),
            "fieldtype": "Float",
            "precision": 6,
            "width": 120,
        },
    ]

    # One column per configured dimension. The column's options point at the
    # dim_N_doctype field so each row resolves its own link target.
    for idx, dim in enumerate(config.dimensions or [], start=1):
        if idx > MAX_DIMENSIONS:
            break
        columns.append(
            {
                "fieldname": f"dim_{idx}",
                "label": dim.label or dim.dimension_fieldname,
                "fieldtype": "Dynamic Link",
                "options": f"dim_{idx}_doctype",
                "width": 150,
            }
        )

    return columns


# ----------------------------------------------------------------------
# Data construction
# ----------------------------------------------------------------------

def _build_data(config, filters: dict) -> list[dict]:
    """Build the list of report rows for the given filters."""
    source_name = filters.get("source_name")
    group_by_source = filters.get("group_by_source")

    if source_name:
        # Single-source view: opening row, entries, closing row.
        return _rows_for_source(config, source_name, filters)

    if group_by_source:
        # Grouped view: one block per source that has matching entries.
        return _grouped_rows(config, filters)

    # Flat view: just chronological entries across all matching sources.
    return _flat_entry_rows(config, filters)


def _rows_for_source(config, source_name: str, filters: dict) -> list[dict]:
    """Opening row + entries + closing row for one source."""
    opening = _opening_balance(config.name, source_name, filters.get("from_date"))
    entries = _query_entries(
        config_name=config.name,
        filters=filters,
        source_name=source_name,
    )

    rows: list[dict] = []
    rows.append(_balance_row(_("Opening Balance"), source_name, opening))
    rows.extend(_entry_to_row(e) for e in entries)
    closing = entries[-1][FN_BALANCE] if entries else opening
    rows.append(_balance_row(_("Closing Balance"), source_name, closing))
    return rows


def _grouped_rows(config, filters: dict) -> list[dict]:
    """One block per source: opening, entries, closing — sorted alphabetically by source."""
    source_names = _sources_with_entries_in_window(config.name, filters)

    rows: list[dict] = []
    for source_name in source_names:
        rows.extend(_rows_for_source(config, source_name, filters))
    return rows


def _flat_entry_rows(config, filters: dict) -> list[dict]:
    """All matching entries, ordered chronologically. No opening/closing."""
    entries = _query_entries(config_name=config.name, filters=filters)
    return [_entry_to_row(e) for e in entries]


# ----------------------------------------------------------------------
# Queries
# ----------------------------------------------------------------------

def _query_entries(
    *,
    config_name: str,
    filters: dict,
    source_name: str | None = None,
) -> list[dict]:
    """Return submitted Ledger Entry rows matching the filters.

    Always excludes cancelled entries (docstatus != 2).
    """
    base_filters: dict = {
        "ledger_config": config_name,
        "docstatus": 1,  # Submitted only; excludes draft (0) and cancelled (2).
    }

    if source_name:
        base_filters[FN_SOURCE_NAME] = source_name

    if filters.get("from_date"):
        base_filters.setdefault(FN_POSTING_DATE, [])
        base_filters[FN_POSTING_DATE] = [">=", filters["from_date"]]

    if filters.get("to_date"):
        existing = base_filters.get(FN_POSTING_DATE)
        if existing and isinstance(existing, list) and existing[0] == ">=":
            base_filters[FN_POSTING_DATE] = [
                "between",
                [existing[1], filters["to_date"]],
            ]
        else:
            base_filters[FN_POSTING_DATE] = ["<=", filters["to_date"]]

    # Dimension filters.
    for idx in range(1, MAX_DIMENSIONS + 1):
        key = f"dim_{idx}"
        if filters.get(key):
            base_filters[key] = filters[key]

    fields = [
        "name",
        FN_POSTING_DATE,
        FN_POSTING_TIME,
        FN_POSTING_DATETIME,
        FN_SOURCE_DOCTYPE,
        FN_SOURCE_NAME,
        FN_VALUE,
        FN_DELTA,
        FN_BALANCE,
    ] + [f"dim_{i}" for i in range(1, MAX_DIMENSIONS + 1)] + [
        f"dim_{i}_doctype" for i in range(1, MAX_DIMENSIONS + 1)
    ]

    return frappe.get_all(
        "Ledger Entry",
        filters=base_filters,
        fields=fields,
        order_by=f"{FN_SOURCE_NAME} asc, {FN_POSTING_DATETIME} asc",
    )


def _sources_with_entries_in_window(config_name: str, filters: dict) -> list[str]:
    """Return distinct source_name values with at least one entry in the window."""
    base_filters: dict = {
        "ledger_config": config_name,
        "docstatus": 1,
    }
    if filters.get("from_date"):
        base_filters[FN_POSTING_DATE] = [">=", filters["from_date"]]
    if filters.get("to_date"):
        existing = base_filters.get(FN_POSTING_DATE)
        if existing and isinstance(existing, list) and existing[0] == ">=":
            base_filters[FN_POSTING_DATE] = [
                "between",
                [existing[1], filters["to_date"]],
            ]
        else:
            base_filters[FN_POSTING_DATE] = ["<=", filters["to_date"]]
    for idx in range(1, MAX_DIMENSIONS + 1):
        key = f"dim_{idx}"
        if filters.get(key):
            base_filters[key] = filters[key]

    rows = frappe.get_all(
        "Ledger Entry",
        filters=base_filters,
        fields=[FN_SOURCE_NAME],
        group_by=FN_SOURCE_NAME,
        order_by=f"{FN_SOURCE_NAME} asc",
    )
    return [r[FN_SOURCE_NAME] for r in rows]


def _opening_balance(config_name: str, source_name: str, from_date) -> float:
    """Balance of the last submitted entry before from_date for this source.

    Note: deliberately ignores dimension filters. Balance is per-source.
    If no from_date is supplied, opening is 0 (the report shows full history).
    """
    if not from_date:
        return 0.0

    rows = frappe.get_all(
        "Ledger Entry",
        filters={
            "ledger_config": config_name,
            FN_SOURCE_NAME: source_name,
            "docstatus": 1,
            FN_POSTING_DATE: ["<", from_date],
        },
        fields=[FN_BALANCE],
        order_by=f"{FN_POSTING_DATETIME} desc",
        limit=1,
    )
    return flt(rows[0][FN_BALANCE]) if rows else 0.0


# ----------------------------------------------------------------------
# Row formatting
# ----------------------------------------------------------------------

def _entry_to_row(entry: dict) -> dict:
    """Convert a Ledger Entry dict from the DB into a report row dict."""
    row = {
        FN_POSTING_DATE: entry[FN_POSTING_DATE],
        FN_POSTING_TIME: entry[FN_POSTING_TIME],
        FN_SOURCE_DOCTYPE: entry[FN_SOURCE_DOCTYPE],
        FN_SOURCE_NAME: entry[FN_SOURCE_NAME],
        FN_VALUE: flt(entry[FN_VALUE]),
        FN_DELTA: flt(entry[FN_DELTA]),
        FN_BALANCE: flt(entry[FN_BALANCE]),
    }
    for idx in range(1, MAX_DIMENSIONS + 1):
        row[f"dim_{idx}"] = entry.get(f"dim_{idx}")
        row[f"dim_{idx}_doctype"] = entry.get(f"dim_{idx}_doctype")
    return row


def _balance_row(label: str, source_name: str, balance: float) -> dict:
    """Build a synthetic opening/closing row.

    These rows have no posting date/time and no delta — they're summary
    markers. The label goes in the Source Document column for visibility.
    """
    return {
        FN_POSTING_DATE: None,
        FN_POSTING_TIME: None,
        FN_SOURCE_DOCTYPE: None,
        FN_SOURCE_NAME: f"{label}: {source_name}",
        FN_VALUE: None,
        FN_DELTA: None,
        FN_BALANCE: flt(balance),
    }
