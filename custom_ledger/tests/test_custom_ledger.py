# Copyright (c) 2026, Custom Ledger Contributors
# License: TBD. See license.txt

import unittest

import frappe
from frappe.utils import flt

from custom_ledger.custom_ledger.report.custom_ledger.custom_ledger import execute
from custom_ledger.tests.test_ledger_config import (
    FIXTURE_DOCTYPE,
    _ensure_fixture_doctypes,
)


def _make_config(name="Report Test Config"):
    existing = frappe.db.exists("Ledger Config", {"ledger_name": name})
    if existing:
        return frappe.get_doc("Ledger Config", existing)

    config = frappe.get_doc(
        {
            "doctype": "Ledger Config",
            "ledger_name": name,
            "ledger_type": "Track changes to a field",
            "source_doctype": FIXTURE_DOCTYPE,
            "value_source_mode": "Field on document",
            "tracked_field": "tracked_value",
            "posting_date_source": "Document modification time",
            "is_active": 1,
        }
    )
    config.insert(ignore_permissions=True)
    return config


def _make_source(value: float):
    doc = frappe.get_doc(
        {
            "doctype": FIXTURE_DOCTYPE,
            "tracked_value": value,
            "notes": "report test",
        }
    )
    doc.insert(ignore_permissions=True)
    return doc


@unittest.skipUnless(
    frappe.conf.get("developer_mode"),
    "Report tests require developer_mode=1 to create fixture DocTypes.",
)
class TestCustomLedgerReport(unittest.TestCase):
    """End-to-end tests for the Custom Ledger report's execute() function."""

    @classmethod
    def setUpClass(cls):
        _ensure_fixture_doctypes()

    def setUp(self):
        for name in frappe.get_all("Ledger Entry", pluck="name"):
            entry = frappe.get_doc("Ledger Entry", name)
            if entry.docstatus == 1:
                entry.cancel()
            entry.delete(ignore_permissions=True)
        for name in frappe.get_all(
            "Ledger Config", filters={"ledger_name": ["like", "Report %"]}, pluck="name"
        ):
            frappe.delete_doc("Ledger Config", name, ignore_permissions=True)
        for name in frappe.get_all(FIXTURE_DOCTYPE, pluck="name"):
            frappe.delete_doc(FIXTURE_DOCTYPE, name, ignore_permissions=True)
        frappe.cache().delete_keys("custom_ledger:configs_for:*")
        frappe.db.commit()

    # ------------------------------------------------------------------
    # No config / empty cases
    # ------------------------------------------------------------------

    def test_empty_when_no_config_filter(self):
        columns, data = execute({})
        self.assertEqual(columns, [])
        self.assertEqual(data, [])

    def test_empty_when_no_entries(self):
        config = _make_config()
        columns, data = execute({"ledger_config": config.name})
        # Columns still present; data empty.
        self.assertTrue(columns)
        self.assertEqual(data, [])

    # ------------------------------------------------------------------
    # Flat view (no source filter, group_by_source unchecked)
    # ------------------------------------------------------------------

    def test_flat_view_returns_chronological_entries(self):
        config = _make_config()
        a = _make_source(100.0)
        b = _make_source(200.0)
        b.tracked_value = 220.0
        b.save(ignore_permissions=True)

        columns, data = execute({"ledger_config": config.name})
        self.assertEqual(len(data), 3)
        # Rows are real entries (no opening/closing markers).
        self.assertTrue(all(r.get("source_name") in (a.name, b.name) for r in data))

    # ------------------------------------------------------------------
    # Source-filtered view
    # ------------------------------------------------------------------

    def test_source_view_includes_opening_and_closing_rows(self):
        config = _make_config()
        source = _make_source(100.0)
        source.tracked_value = 110.0
        source.save(ignore_permissions=True)

        columns, data = execute(
            {"ledger_config": config.name, "source_name": source.name}
        )

        # 2 entries plus opening and closing = 4 rows.
        self.assertEqual(len(data), 4)

        # First row is opening, last is closing.
        self.assertIn("Opening Balance", data[0]["source_name"])
        self.assertIn("Closing Balance", data[-1]["source_name"])

        # Closing balance equals the last entry's balance.
        self.assertEqual(flt(data[-1]["balance"]), flt(data[-2]["balance"]))

    def test_opening_balance_uses_pre_window_entry(self):
        """Opening balance should reflect entries before from_date."""
        config = _make_config()
        source = _make_source(50.0)
        # Force two entries with different dates.
        source.tracked_value = 70.0
        source.save(ignore_permissions=True)

        all_entries = frappe.get_all(
            "Ledger Entry",
            filters={"source_name": source.name, "docstatus": 1},
            fields=["name", "posting_date", "balance"],
            order_by="posting_datetime asc",
        )
        # Move the first entry's posting_date into the past for a clean test.
        from frappe.utils import add_days, getdate, today

        first = all_entries[0]
        past = add_days(getdate(today()), -5)
        frappe.db.set_value("Ledger Entry", first["name"], "posting_date", past)
        frappe.db.set_value(
            "Ledger Entry",
            first["name"],
            "posting_datetime",
            f"{past} 00:00:00",
        )
        frappe.db.commit()

        columns, data = execute(
            {
                "ledger_config": config.name,
                "source_name": source.name,
                "from_date": today(),
            }
        )

        # Opening row should reflect the pre-window entry's balance (50).
        opening = data[0]
        self.assertEqual(flt(opening["balance"]), 50.0)

    # ------------------------------------------------------------------
    # Cancelled entries are hidden
    # ------------------------------------------------------------------

    def test_cancelled_entries_excluded(self):
        config = _make_config()
        source = _make_source(100.0)
        # Cancel its only entry.
        entry_name = frappe.get_all(
            "Ledger Entry",
            filters={"source_name": source.name, "docstatus": 1},
            pluck="name",
        )[0]
        frappe.get_doc("Ledger Entry", entry_name).cancel()
        frappe.db.commit()

        columns, data = execute({"ledger_config": config.name})
        self.assertEqual(data, [])

    # ------------------------------------------------------------------
    # Group-by-source
    # ------------------------------------------------------------------

    def test_group_by_source_produces_blocks_per_source(self):
        config = _make_config()
        a = _make_source(100.0)
        b = _make_source(200.0)

        columns, data = execute(
            {"ledger_config": config.name, "group_by_source": 1}
        )

        # Two sources, each with: opening + 1 entry + closing = 3 rows.
        self.assertEqual(len(data), 6)

        # First and last row in each block are summary rows.
        labels = [r["source_name"] for r in data]
        opening_count = sum(1 for l in labels if "Opening Balance" in l)
        closing_count = sum(1 for l in labels if "Closing Balance" in l)
        self.assertEqual(opening_count, 2)
        self.assertEqual(closing_count, 2)

    # ------------------------------------------------------------------
    # Filter validation
    # ------------------------------------------------------------------

    def test_invalid_date_range_raises(self):
        config = _make_config()
        with self.assertRaises(frappe.ValidationError):
            execute(
                {
                    "ledger_config": config.name,
                    "from_date": "2026-12-31",
                    "to_date": "2026-01-01",
                }
            )

    # ------------------------------------------------------------------
    # Columns
    # ------------------------------------------------------------------

    def test_columns_include_base_set(self):
        config = _make_config()
        columns, _data = execute({"ledger_config": config.name})
        fieldnames = {c["fieldname"] for c in columns}
        for required in (
            "posting_date",
            "posting_time",
            "source_name",
            "value",
            "delta",
            "balance",
        ):
            self.assertIn(required, fieldnames)

    def test_dimension_columns_appended(self):
        config = _make_config(name="Report Dims Config")
        config.append("dimensions", {"dimension_fieldname": "category"})
        config.save(ignore_permissions=True)

        columns, _data = execute({"ledger_config": config.name})
        fieldnames = {c["fieldname"] for c in columns}
        self.assertIn("dim_1", fieldnames)
