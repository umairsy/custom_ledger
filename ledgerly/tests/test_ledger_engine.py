# Copyright (c) 2026, Ledgerly Contributors
# License: TBD. See license.txt

import unittest

import frappe
from frappe.utils import flt

from ledgerly.core.engine_value_snapshot import (
    _get_active_configs_for_doctype,
    invalidate_config_cache,
)
from ledgerly.tests.test_ledger_config import (
    FIXTURE_DOCTYPE,
    _ensure_fixture_doctypes,
)


def _make_config(name, **overrides):
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
            **overrides,
        }
    )
    config.insert(ignore_permissions=True)
    return config


def _make_source_doc(**fields):
    base = {"doctype": FIXTURE_DOCTYPE, "tracked_value": 0.0, "notes": "engine test"}
    base.update(fields)
    doc = frappe.get_doc(base)
    doc.insert(ignore_permissions=True)
    return doc


def _entries_for(config_name, source_name):
    return frappe.get_all(
        "Ledger Entry",
        filters={"ledger_config": config_name, "source_name": source_name, "docstatus": 1},
        fields=["name", "value", "delta", "balance", "posting_datetime"],
        order_by="posting_datetime asc, creation asc",
    )


@unittest.skipUnless(
    frappe.conf.get("developer_mode"),
    "Engine tests require developer_mode=1 to create fixture DocTypes.",
)
class TestLedgerEngine(unittest.TestCase):

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
            "Ledger Config", filters={"ledger_name": ["like", "Engine %"]}, pluck="name"
        ):
            frappe.delete_doc("Ledger Config", name, ignore_permissions=True)
        for name in frappe.get_all(FIXTURE_DOCTYPE, pluck="name"):
            frappe.delete_doc(FIXTURE_DOCTYPE, name, ignore_permissions=True)
        frappe.cache().delete_keys("ledgerly:configs_for:*")
        frappe.db.commit()

    def test_first_insert_creates_entry(self):
        _make_config("Engine First Insert")
        source = _make_source_doc(tracked_value=120.0)
        entries = _entries_for("Engine First Insert", source.name)
        self.assertEqual(len(entries), 1)
        self.assertEqual(flt(entries[0].value), 120.0)
        self.assertEqual(flt(entries[0].delta), 120.0)
        self.assertEqual(flt(entries[0].balance), 120.0)

    def test_update_creates_entry_with_delta(self):
        _make_config("Engine Update")
        source = _make_source_doc(tracked_value=120.0)
        source.tracked_value = 123.0
        source.save(ignore_permissions=True)

        entries = _entries_for("Engine Update", source.name)
        self.assertEqual(len(entries), 2)
        self.assertEqual(flt(entries[1].value), 123.0)
        self.assertEqual(flt(entries[1].delta), 3.0)
        self.assertEqual(flt(entries[1].balance), 123.0)

    def test_no_entry_when_tracked_value_unchanged(self):
        _make_config("Engine No Change")
        source = _make_source_doc(tracked_value=100.0)
        source.notes = "different notes, same weight"
        source.save(ignore_permissions=True)

        entries = _entries_for("Engine No Change", source.name)
        self.assertEqual(len(entries), 1)

    def test_inactive_config_skipped(self):
        _make_config("Engine Inactive", is_active=0)
        source = _make_source_doc(tracked_value=50.0)
        entries = _entries_for("Engine Inactive", source.name)
        self.assertEqual(len(entries), 0)

    def test_multiple_configs_each_get_entry(self):
        _make_config("Engine Multi A", tracked_field="tracked_value")
        _make_config("Engine Multi B", tracked_field="tracked_int")
        source = _make_source_doc(tracked_value=10.0, tracked_int=20)

        a_entries = _entries_for("Engine Multi A", source.name)
        b_entries = _entries_for("Engine Multi B", source.name)
        self.assertEqual(len(a_entries), 1)
        self.assertEqual(len(b_entries), 1)
        self.assertEqual(flt(a_entries[0].value), 10.0)
        self.assertEqual(flt(b_entries[0].value), 20.0)

    def test_dimensions_populated_on_entry(self):
        config = _make_config("Engine With Dims")
        config.append("dimensions", {"dimension_fieldname": "category"})
        config.save(ignore_permissions=True)
        source = _make_source_doc(tracked_value=42.0, category="Item")

        entries = frappe.get_all(
            "Ledger Entry",
            filters={"ledger_config": "Engine With Dims", "source_name": source.name},
            fields=["dim_1", "dim_1_doctype"],
        )
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].dim_1, "Item")
        self.assertEqual(entries[0].dim_1_doctype, "DocType")

    def test_child_table_sum_mode(self):
        _make_config(
            "Engine Child Sum",
            value_source_mode="Sum across child rows",
            child_table_field="lines",
            tracked_field="weight",
        )
        source = frappe.get_doc(
            {
                "doctype": FIXTURE_DOCTYPE,
                "notes": "child sum test",
                "lines": [
                    {"weight": 10.0, "label": "row A"},
                    {"weight": 25.5, "label": "row B"},
                ],
            }
        )
        source.insert(ignore_permissions=True)

        entries = _entries_for("Engine Child Sum", source.name)
        self.assertEqual(len(entries), 1)
        self.assertEqual(flt(entries[0].value), 35.5)

    def test_balance_accumulates_correctly_over_multiple_updates(self):
        _make_config("Engine Balance")
        source = _make_source_doc(tracked_value=100.0)
        source.tracked_value = 105.0
        source.save(ignore_permissions=True)
        source.tracked_value = 110.0
        source.save(ignore_permissions=True)
        source.tracked_value = 108.0
        source.save(ignore_permissions=True)

        entries = _entries_for("Engine Balance", source.name)
        self.assertEqual(len(entries), 4)
        balances = [flt(e.balance) for e in entries]
        self.assertEqual(balances, [100.0, 105.0, 110.0, 108.0])
