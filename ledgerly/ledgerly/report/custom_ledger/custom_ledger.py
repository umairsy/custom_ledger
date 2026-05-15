# Copyright (c) 2026, Ledgerly Contributors
# License: TBD. See license.txt
"""Custom Ledger report — redesign (PR #7 rev 2).

Column order: Posting Date | Time | <Source DocType> | Narration* | Opening | Delta | Balance
  * only when config.narration_field is set

Row types:
  _row_type = "opening"  — amber summary row at top (balance as of From Date)
  _row_type = "data"     — body entry rows
  _row_type = "closing"  — amber summary row at bottom (final balance + net delta)

Math invariant on every data row: Opening + Delta = Balance
  Implemented as: opening = balance - delta  (always exact, no cross-row state)

Opening balance row: sum of each source's last entry balance before From Date.
Closing balance row: sum of each source's last entry balance in the window,
  plus net delta (= sum of all deltas in the window).

Narration: batch-fetched in one extra query to avoid N+1.

Sort: posting_datetime ASC, name ASC (tiebreaker) — hardcoded; correctness requirement.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import flt, getdate

FN_POSTING_DATE = "posting_date"
FN_POSTING_TIME = "posting_time"
FN_POSTING_DATETIME = "posting_datetime"
FN_SOURCE_DOCTYPE = "source_doctype"
FN_SOURCE_NAME = "source_name"
FN_DELTA = "delta"
FN_BALANCE = "balance"
FN_OPENING = "opening"
FN_NARRATION = "narration"

MAX_DIMENSIONS = 5
NARRATION_MAX_LEN = 80
DEFAULT_PRECISION = 2


def execute(filters: dict | None = None):
    """Frappe Script Report entry point. Returns (columns, data)."""
    filters = filters or {}

    if not filters.get("ledger_config"):
        return [], []

    config = frappe.get_cached_doc("Ledger Config", filters["ledger_config"])
    _validate_filters(filters)

    columns = _build_columns(config)
    data = _build_data(config, filters)
    return columns, data


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def _validate_filters(filters: dict) -> None:
    from_date = filters.get("from_date")
    to_date = filters.get("to_date")
    if from_date and to_date and getdate(to_date) < getdate(from_date):
        frappe.throw(_("To Date cannot be earlier than From Date."))


# ---------------------------------------------------------------------------
# Columns
# ---------------------------------------------------------------------------

def _build_columns(config) -> list[dict]:
    precision = _get_field_precision(config)

    cols = [
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
            "width": 80,
        },
        {
            # Hidden helper column so Dynamic Link can resolve its doctype.
            "fieldname": FN_SOURCE_DOCTYPE,
            "label": _("Source DocType"),
            "fieldtype": "Data",
            "hidden": 1,
            "width": 0,
        },
        {
            "fieldname": FN_SOURCE_NAME,
            "label": _(config.source_doctype),
            "fieldtype": "Dynamic Link",
            "options": FN_SOURCE_DOCTYPE,
            "width": 200,
        },
    ]

    cols += [
        {
            "fieldname": FN_OPENING,
            "label": _("Opening"),
            "fieldtype": "Float",
            "precision": precision,
            "width": 130,
        },
        {
            "fieldname": FN_DELTA,
            "label": _("Delta"),
            "fieldtype": "Float",
            "precision": precision,
            "width": 120,
        },
        {
            "fieldname": FN_BALANCE,
            "label": _("Balance"),
            "fieldtype": "Float",
            "precision": precision,
            "width": 130,
        },
    ]

    # Narration and dimensions come after the numeric columns so the
    # Opening → Delta → Balance flow is uninterrupted when scanning.
    if config.narration_field:
        cols.append(
            {
                "fieldname": FN_NARRATION,
                "label": _("Narration"),
                "fieldtype": "Data",
                "width": 220,
            }
        )

    # Dimension columns — one per configured dim.
    for idx, dim in enumerate(config.dimensions or [], start=1):
        if idx > MAX_DIMENSIONS:
            break
        cols.append(
            {
                "fieldname": f"dim_{idx}",
                "label": dim.label or dim.dimension_fieldname,
                "fieldtype": "Dynamic Link",
                "options": f"dim_{idx}_doctype",
                "width": 150,
            }
        )

    return cols


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------

def _build_data(config, filters: dict) -> list[dict]:
    entries = _query_entries(config, filters)
    has_narration = bool(config.narration_field)

    # Opening balance: sum of each source's last balance before From Date.
    total_opening = _total_opening_balance(
        config.name, entries, filters.get("from_date")
    )

    rows: list[dict] = []

    # Opening summary row.
    rows.append(_summary_row("opening", _("Opening Balance"), total_opening, None, has_narration))

    # Body rows — narration is read directly from the Ledger Entry row
    # (stored at creation time from the source doc, so it is immutable).
    for entry in entries:
        opening = flt(entry[FN_BALANCE]) - flt(entry[FN_DELTA])
        rows.append(_entry_row(entry, opening, has_narration, config))

    # Closing summary row.
    net_delta = sum(flt(e[FN_DELTA]) for e in entries)
    # Final balance: last-seen balance per source (iteration is datetime asc,
    # so last occurrence wins — correct).
    final_per_source: dict[str, float] = {}
    for e in entries:
        final_per_source[e[FN_SOURCE_NAME]] = flt(e[FN_BALANCE])
    total_final = sum(final_per_source.values()) if final_per_source else total_opening

    rows.append(
        _summary_row("closing", _("Closing Balance"), total_final, net_delta, has_narration)
    )

    return rows


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------

def _parse_multiselect(val) -> list[str] | None:
    """Normalise a MultiSelectList filter value to a list of strings, or None if empty."""
    if not val:
        return None
    if isinstance(val, list):
        items = [v.get("value", v) if isinstance(v, dict) else v for v in val]
        items = [str(i) for i in items if i]
        return items or None
    # Single string (single-select fallback or plain value).
    return [str(val)] if val else None


def _apply_multiselect(base: dict, fieldname: str, val) -> None:
    """Add an IN or equality filter for a (potentially multi-valued) field."""
    parsed = _parse_multiselect(val)
    if not parsed:
        return
    base[fieldname] = ["in", parsed] if len(parsed) > 1 else parsed[0]


def _query_entries(config, filters: dict) -> list[dict]:
    """Return submitted Ledger Entry rows for this config + filters.

    Sort: posting_datetime ASC, name ASC — hardcoded correctness requirement.
    Cancelled entries (docstatus=2) are always excluded.
    """
    base: dict = {
        "ledger_config": config.name,
        "docstatus": 1,
    }

    _apply_multiselect(base, FN_SOURCE_NAME, filters.get("source_name"))

    from_date = filters.get("from_date")
    to_date = filters.get("to_date")

    if from_date and to_date:
        base[FN_POSTING_DATE] = ["between", [from_date, to_date]]
    elif from_date:
        base[FN_POSTING_DATE] = [">=", from_date]
    elif to_date:
        base[FN_POSTING_DATE] = ["<=", to_date]

    for idx in range(1, MAX_DIMENSIONS + 1):
        _apply_multiselect(base, f"dim_{idx}", filters.get(f"dim_{idx}"))

    fields = [
        "name",
        FN_POSTING_DATE,
        FN_POSTING_TIME,
        FN_POSTING_DATETIME,
        FN_SOURCE_DOCTYPE,
        FN_SOURCE_NAME,
        FN_DELTA,
        FN_BALANCE,
        FN_NARRATION,
    ] + [f"dim_{i}" for i in range(1, MAX_DIMENSIONS + 1)] + [
        f"dim_{i}_doctype" for i in range(1, MAX_DIMENSIONS + 1)
    ]

    return frappe.get_all(
        "Ledger Entry",
        filters=base,
        fields=fields,
        order_by=f"{FN_POSTING_DATETIME} asc, name asc",
    )



def _opening_balance(config_name: str, source_name: str, from_date) -> float:
    """Last submitted balance for this source strictly before from_date."""
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


def _total_opening_balance(
    config_name: str, entries: list[dict], from_date
) -> float:
    """Sum of pre-period opening balances for every source that appears in entries."""
    if not from_date or not entries:
        return 0.0
    source_names = list({e[FN_SOURCE_NAME] for e in entries})
    return sum(_opening_balance(config_name, sn, from_date) for sn in source_names)


# ---------------------------------------------------------------------------
# Precision
# ---------------------------------------------------------------------------

def _get_field_precision(config) -> int:
    """Return display precision for numeric columns.

    Reads the precision attribute from the tracked field's docfield definition.
    Falls back to DEFAULT_PRECISION (2) when unset or on any error.
    """
    try:
        target_doctype = config.source_doctype
        if config.value_source_mode == "Sum across child rows" and config.child_table_field:
            parent_meta = frappe.get_meta(config.source_doctype)
            child_df = parent_meta.get_field(config.child_table_field)
            if child_df:
                target_doctype = child_df.options

        meta = frappe.get_meta(target_doctype)
        df = meta.get_field(config.tracked_field)
        if df and df.precision is not None and str(df.precision).strip():
            return int(df.precision)
    except Exception:
        pass
    return DEFAULT_PRECISION


# ---------------------------------------------------------------------------
# Row builders
# ---------------------------------------------------------------------------

def _entry_row(
    entry: dict,
    opening: float,
    has_narration: bool,
    config,
) -> dict:
    row = {
        "_row_type": "data",
        FN_POSTING_DATE: entry[FN_POSTING_DATE],
        FN_POSTING_TIME: entry[FN_POSTING_TIME],
        FN_SOURCE_DOCTYPE: entry[FN_SOURCE_DOCTYPE],
        FN_SOURCE_NAME: entry[FN_SOURCE_NAME],
        FN_OPENING: flt(opening),
        FN_DELTA: flt(entry[FN_DELTA]),
        FN_BALANCE: flt(entry[FN_BALANCE]),
    }
    if has_narration:
        raw = entry.get(FN_NARRATION) or ""
        row[FN_NARRATION] = raw[:NARRATION_MAX_LEN] + "…" if len(raw) > NARRATION_MAX_LEN else raw

    for idx in range(1, MAX_DIMENSIONS + 1):
        row[f"dim_{idx}"] = entry.get(f"dim_{idx}")
        row[f"dim_{idx}_doctype"] = entry.get(f"dim_{idx}_doctype")

    return row


def _summary_row(
    row_type: str,
    label: str,
    balance: float,
    delta: float | None,
    has_narration: bool,
) -> dict:
    """Opening or Closing amber summary row."""
    row = {
        "_row_type": row_type,
        FN_POSTING_DATE: None,
        FN_POSTING_TIME: None,
        FN_SOURCE_DOCTYPE: None,
        FN_SOURCE_NAME: label,
        FN_OPENING: balance if row_type == "opening" else None,
        FN_DELTA: flt(delta) if delta is not None else None,
        FN_BALANCE: flt(balance),
    }
    if has_narration:
        row[FN_NARRATION] = None
    for idx in range(1, MAX_DIMENSIONS + 1):
        row[f"dim_{idx}"] = None
        row[f"dim_{idx}_doctype"] = None
    return row
