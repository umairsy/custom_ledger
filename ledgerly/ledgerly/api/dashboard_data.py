# Copyright (c) 2026, Ledgerly Contributors
# License: TBD. See license.txt
"""Dashboard data API — single endpoint returns all six chart datasets.

All charts for a given Ledger Config are computed from one frappe.get_all
query so filter changes cost exactly one round-trip.

Carry-forward rule (trend chart): empty time buckets inherit the previous
bucket's balance rather than resetting to zero. This keeps sparse datasets
visually flat instead of zigzagging to the baseline.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, getdate, get_first_day, today

MAX_SERIES = 8
MAX_BARS = 15
_DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

_FIELDS = [
    "name",
    "posting_date",
    "posting_datetime",
    "source_doctype",
    "source_name",
    "delta",
    "balance",
    "narration",
] + [f"dim_{i}" for i in range(1, 6)] + [f"dim_{i}_doctype" for i in range(1, 6)]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_dashboard_meta(config_name: str) -> dict:
    """Config metadata needed to render the filter bar (dimensions, doctype, etc.)."""
    if not frappe.has_permission("Ledger Config", "read", config_name):
        frappe.throw(_("Insufficient permissions to read Ledger Config '{0}'.").format(config_name))

    config = frappe.get_cached_doc("Ledger Config", config_name)
    return {
        "ledger_name": config.ledger_name,
        "source_doctype": config.source_doctype,
        "narration_field": config.narration_field,
        "precision": _get_precision(config),
        "dimensions": [
            {
                "fieldname": f"dim_{i}",
                "label": dim.label or dim.link_doctype,
                "link_doctype": dim.link_doctype,
            }
            for i, dim in enumerate(config.dimensions or [], start=1)
            if i <= 5
        ],
    }


@frappe.whitelist()
def get_dashboard_data(config_name: str, filters: str | dict) -> dict:
    """Return data for all six dashboard charts in one call.

    Args:
        config_name: Ledger Config name.
        filters: JSON string (from frontend) or dict with keys:
            from_date, to_date, time_grain, group_by,
            source_name (str or list), dim_1..5 (str or list).
    """
    if not frappe.has_permission("Ledger Config", "read", config_name):
        frappe.throw(_("Insufficient permissions."))

    config = frappe.get_cached_doc("Ledger Config", config_name)
    filters = json.loads(filters) if isinstance(filters, str) else (filters or {})

    from_date = filters.get("from_date") or get_first_day(today())
    to_date = filters.get("to_date") or today()
    time_grain = filters.get("time_grain") or "day"
    group_by = filters.get("group_by") or "none"

    base = {
        "ledger_config": config_name,
        "docstatus": 1,
        "posting_date": ["between", [from_date, to_date]],
    }
    _apply_multifilter(base, "source_name", filters.get("source_name"))
    for i in range(1, 6):
        _apply_multifilter(base, f"dim_{i}", filters.get(f"dim_{i}"))

    entries = frappe.get_all(
        "Ledger Entry",
        filters=base,
        fields=_FIELDS,
        order_by="posting_datetime asc, name asc",
    )

    precision = _get_precision(config)

    return {
        "kpi": _compute_kpi(entries, config_name, from_date, precision),
        "trend": _compute_trend(entries, time_grain, group_by, from_date, to_date),
        "breakdown": _compute_breakdown(entries, group_by),
        "top_movers": _compute_top_movers(entries, config),
        "distribution": _compute_distribution(entries, precision),
        "heatmap": _compute_heatmap(entries),
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _apply_multifilter(base: dict, fieldname: str, val) -> None:
    if not val:
        return
    if isinstance(val, list):
        items = [v.get("value", v) if isinstance(v, dict) else str(v) for v in val]
        items = [i for i in items if i]
    else:
        items = [str(val)] if val else []
    if items:
        base[fieldname] = ["in", items] if len(items) > 1 else items[0]


def _get_precision(config) -> int:
    try:
        target = config.source_doctype
        if config.value_source_mode == "Sum across child rows" and config.child_table_field:
            child_df = frappe.get_meta(config.source_doctype).get_field(config.child_table_field)
            if child_df:
                target = child_df.options
        df = frappe.get_meta(target).get_field(config.tracked_field)
        if df and df.precision is not None and str(df.precision).strip():
            return int(df.precision)
    except Exception:
        pass
    return 2


def _get_group_value(entry: dict, group_by: str) -> str:
    if group_by == "none":
        return "Total"
    if group_by == "source":
        return entry.get("source_name") or ""
    if group_by == "narration":
        return (entry.get("narration") or "").strip() or "(no narration)"
    if group_by.startswith("dim_"):
        return entry.get(group_by) or "(none)"
    return "Total"


# ---------------------------------------------------------------------------
# Time bucketing
# ---------------------------------------------------------------------------

def _bucket_dt(dt: datetime, grain: str) -> str:
    if grain == "hour":
        return dt.strftime("%Y-%m-%d %H:00")
    if grain == "week":
        iso = dt.isocalendar()
        return f"{iso[0]}-W{iso[1]:02d}"
    if grain == "month":
        return dt.strftime("%Y-%m")
    if grain == "quarter":
        q = (dt.month - 1) // 3 + 1
        return f"{dt.year}-Q{q}"
    if grain == "year":
        return str(dt.year)
    return dt.strftime("%Y-%m-%d")


def _generate_buckets(from_date, to_date, grain: str) -> list[str]:
    start = datetime.combine(getdate(from_date), datetime.min.time())
    end = datetime.combine(getdate(to_date), datetime.min.time())

    buckets: list[str] = []
    cur = start
    while cur <= end:
        bk = _bucket_dt(cur, grain)
        if not buckets or buckets[-1] != bk:
            buckets.append(bk)
        if grain == "hour":
            cur += timedelta(hours=1)
        elif grain == "week":
            cur += timedelta(weeks=1)
        elif grain == "month":
            m = cur.month + 1
            y = cur.year + (m - 1) // 12
            cur = cur.replace(year=y, month=((m - 1) % 12) + 1, day=1)
        elif grain == "quarter":
            m = cur.month + 3
            y = cur.year + (m - 1) // 12
            cur = cur.replace(year=y, month=((m - 1) % 12) + 1, day=1)
        elif grain == "year":
            cur = cur.replace(year=cur.year + 1)
        else:
            cur += timedelta(days=1)
    return buckets


# ---------------------------------------------------------------------------
# KPI Strip
# ---------------------------------------------------------------------------

def _compute_kpi(entries: list[dict], config_name: str, from_date, precision: int) -> dict:
    # Opening: last balance per source strictly before from_date
    opening_rows = frappe.get_all(
        "Ledger Entry",
        filters={"ledger_config": config_name, "docstatus": 1, "posting_date": ["<", from_date]},
        fields=["source_name", "balance", "posting_datetime"],
        order_by="posting_datetime desc",
    )
    opening_per_source: dict[str, float] = {}
    for row in opening_rows:
        sn = row["source_name"]
        if sn not in opening_per_source:
            opening_per_source[sn] = flt(row["balance"])

    # Closing: last balance per source in the period (entries are asc-sorted, last wins)
    closing_per_source: dict[str, float] = {}
    for e in entries:
        closing_per_source[e["source_name"]] = flt(e["balance"])

    total_closing = sum(closing_per_source.values()) if closing_per_source else 0.0
    total_opening = sum(opening_per_source.get(sn, 0.0) for sn in closing_per_source) if closing_per_source else sum(opening_per_source.values())

    total_in = sum(flt(e["delta"]) for e in entries if flt(e["delta"]) > 0)
    total_out = sum(flt(e["delta"]) for e in entries if flt(e["delta"]) < 0)

    return {
        "closing": round(total_closing, precision),
        "net_change": round(total_closing - total_opening, precision),
        "total_in": round(total_in, precision),
        "total_out": round(abs(total_out), precision),
        "records": len(entries),
    }


# ---------------------------------------------------------------------------
# Trend Chart
# ---------------------------------------------------------------------------

def _compute_trend(entries: list[dict], grain: str, group_by: str, from_date, to_date) -> dict:
    buckets = _generate_buckets(from_date, to_date, grain)

    # Collect groups in first-appearance order
    seen: list[str] = []
    for e in entries:
        g = _get_group_value(e, group_by)
        if g not in seen:
            seen.append(g)

    has_others = len(seen) > MAX_SERIES
    top_groups = seen[:MAX_SERIES]
    others_groups = set(seen[MAX_SERIES:]) if has_others else set()

    # Per-group: bucket → last balance in that bucket
    group_bk: dict[str, dict[str, float]] = {g: {} for g in top_groups}
    others_bk: dict[str, float] = {}

    for e in entries:
        dt_val = e.get("posting_datetime")
        if not dt_val:
            continue
        dt = get_datetime(str(dt_val))
        if not isinstance(dt, datetime):
            continue
        bk = _bucket_dt(dt, grain)
        g = _get_group_value(e, group_by)
        bal = flt(e.get("balance", 0))

        if g in group_bk:
            group_bk[g][bk] = bal
        elif g in others_groups:
            # Aggregate others: sum closing balances per bucket (approximation)
            others_bk[bk] = others_bk.get(bk, 0.0) + bal

    colors = [
        "#5DCAA5", "#185FA5", "#F0997B", "#E6C17E",
        "#A78FD0", "#6BB5E5", "#F5A623", "#888888", "#AAAAAA",
    ]

    datasets = []
    for g in top_groups:
        bk_map = group_bk[g]
        series: list[float] = []
        last = 0.0
        for bk in buckets:
            if bk in bk_map:
                last = bk_map[bk]
            series.append(last)
        datasets.append({"name": str(g)[:40], "values": series})

    if has_others:
        series = []
        last = 0.0
        for bk in buckets:
            if bk in others_bk:
                last = others_bk[bk]
            series.append(last)
        datasets.append({"name": f"Others ({len(others_groups)} more)", "values": series})

    return {
        "labels": buckets,
        "datasets": datasets,
        "colors": colors[: len(datasets)],
    }


# ---------------------------------------------------------------------------
# Breakdown
# ---------------------------------------------------------------------------

def _compute_breakdown(entries: list[dict], group_by: str) -> dict:
    if group_by in ("none", "narration"):
        return {"hide": True}

    group_delta: dict[str, float] = {}
    for e in entries:
        g = _get_group_value(e, group_by)
        group_delta[g] = group_delta.get(g, 0.0) + flt(e.get("delta", 0))

    if not group_delta:
        return {"hide": False, "labels": [], "values": [], "colors": []}

    sorted_items = sorted(group_delta.items(), key=lambda x: -abs(x[1]))
    has_others = len(sorted_items) > MAX_BARS
    top = sorted_items[:MAX_BARS]

    if has_others:
        rest_sum = sum(v for _, v in sorted_items[MAX_BARS:])
        top.append((f"Others ({len(sorted_items) - MAX_BARS} more)", rest_sum))

    labels = [str(k)[:35] for k, _ in top]
    values = [round(v, 2) for _, v in top]
    colors = ["#5DCAA5" if v >= 0 else "#F0997B" for v in values]

    return {"hide": False, "labels": labels, "values": values, "colors": colors}


# ---------------------------------------------------------------------------
# Top Movers
# ---------------------------------------------------------------------------

def _compute_top_movers(entries: list[dict], config) -> dict:
    if len(entries) < 3:
        return {"hide": True}

    by_delta_desc = sorted(entries, key=lambda e: -flt(e.get("delta", 0)))
    by_delta_asc = sorted(entries, key=lambda e: flt(e.get("delta", 0)))

    def make_row(e: dict) -> dict:
        return {
            "date": str(e.get("posting_date", "")),
            "source_doctype": e.get("source_doctype", ""),
            "source_name": e.get("source_name", ""),
            "delta": flt(e.get("delta", 0)),
            "narration": (e.get("narration") or "")[:80],
        }

    increases = [make_row(e) for e in by_delta_desc[:5] if flt(e.get("delta", 0)) > 0]
    decreases = [make_row(e) for e in by_delta_asc[:5] if flt(e.get("delta", 0)) < 0]

    return {
        "hide": False,
        "increases": increases,
        "decreases": decreases,
        "has_narration": bool(config.narration_field),
    }


# ---------------------------------------------------------------------------
# Distribution
# ---------------------------------------------------------------------------

def _compute_distribution(entries: list[dict], precision: int) -> dict:
    deltas = [flt(e.get("delta", 0)) for e in entries]
    if len(set(deltas)) < 5:
        return {"hide": True}

    min_d, max_d = min(deltas), max(deltas)
    if min_d == max_d:
        return {"hide": True}

    n_bins = 10
    width = (max_d - min_d) / n_bins
    labels: list[str] = []
    counts: list[int] = [0] * n_bins

    for i in range(n_bins):
        lb = min_d + i * width
        ub = min_d + (i + 1) * width
        labels.append(f"{lb:.{precision}f}–{ub:.{precision}f}")
        for d in deltas:
            if i < n_bins - 1:
                if lb <= d < ub:
                    counts[i] += 1
            else:
                if lb <= d <= ub:
                    counts[i] += 1

    sorted_d = sorted(deltas)
    n = len(sorted_d)
    q1 = sorted_d[n // 4]
    q3 = sorted_d[3 * n // 4]
    subtitle = f"Middle 50% of deltas: {q1:.{precision}f} to {q3:.{precision}f}"

    return {"hide": False, "labels": labels, "values": counts, "subtitle": subtitle}


# ---------------------------------------------------------------------------
# Activity Heatmap
# ---------------------------------------------------------------------------

def _compute_heatmap(entries: list[dict]) -> dict:
    if not entries:
        return {"mode": "strip", "data": [0] * 7, "days": _DAYS}

    dts: list[datetime] = []
    for e in entries:
        dt_val = e.get("posting_datetime")
        if dt_val:
            try:
                dt = get_datetime(str(dt_val))
                if isinstance(dt, datetime):
                    dts.append(dt)
            except Exception:
                pass

    if not dts:
        return {"mode": "strip", "data": [0] * 7, "days": _DAYS}

    # Collapse to strip when time data is meaningless (all midnight)
    all_midnight = len({dt.hour for dt in dts}) <= 1

    if all_midnight:
        day_counts = [0] * 7
        for dt in dts:
            day_counts[dt.weekday()] += 1
        return {"mode": "strip", "data": day_counts, "days": _DAYS}

    grid = [[0] * 24 for _ in range(7)]
    for dt in dts:
        grid[dt.weekday()][dt.hour] += 1

    return {
        "mode": "full",
        "data": grid,
        "days": _DAYS,
        "hours": list(range(24)),
    }
