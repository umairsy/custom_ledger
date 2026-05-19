# Copyright (c) 2026, Ledgerly Contributors
# License: TBD. See license.txt
"""Tests for the balance_display_fields branch of get_field_options."""

import unittest

import frappe

from ledgerly.ledgerly.doctype.ledger_config.ledger_config import get_field_options

CARRIER_DOCTYPE = "Ledgerly Test Carrier"


def _ensure_carrier_fixture():
    """Create a test carrier doctype with both editable and read-only numeric fields.

    Schema:
    - balance (Float, read_only=1)   → should appear in balance_display_fields
    - credit (Currency, read_only=1) → should appear in balance_display_fields
    - qty (Int, read_only=0)         → should appear in tracked_fields
    """
    if frappe.db.exists("DocType", CARRIER_DOCTYPE):
        return
    doc = frappe.get_doc(
        {
            "doctype": "DocType",
            "name": CARRIER_DOCTYPE,
            "module": "Ledgerly",
            "custom": 1,
            "autoname": "hash",
            "fields": [
                {
                    "fieldname": "balance",
                    "fieldtype": "Float",
                    "label": "Balance",
                    "read_only": 1,
                },
                {
                    "fieldname": "credit",
                    "fieldtype": "Currency",
                    "label": "Credit",
                    "read_only": 1,
                },
                {
                    "fieldname": "qty",
                    "fieldtype": "Int",
                    "label": "Quantity",
                    "read_only": 0,
                },
            ],
            "permissions": [
                {
                    "role": "System Manager",
                    "read": 1,
                    "write": 1,
                    "create": 1,
                    "delete": 1,
                }
            ],
        }
    )
    doc.insert(ignore_permissions=True)
    frappe.db.commit()


@unittest.skipUnless(
    frappe.conf.get("developer_mode"),
    "balance_display_fields tests require developer_mode=1 to create fixture DocTypes.",
)
class TestBalanceFieldOptions(unittest.TestCase):
    """The balance_display_fields key should contain only read-only numeric fields."""

    @classmethod
    def setUpClass(cls):
        _ensure_carrier_fixture()

    def test_response_has_both_keys(self):
        result = get_field_options(source_doctype=CARRIER_DOCTYPE)
        self.assertIn("balance_display_fields", result)
        self.assertIn("tracked_fields", result)

    def test_balance_display_fields_contains_read_only_numerics(self):
        result = get_field_options(source_doctype=CARRIER_DOCTYPE)
        balance_values = {f["value"] for f in result["balance_display_fields"]}
        self.assertIn("balance", balance_values)
        self.assertIn("credit", balance_values)

    def test_tracked_fields_contains_editable_numerics(self):
        result = get_field_options(source_doctype=CARRIER_DOCTYPE)
        tracked_values = {f["value"] for f in result["tracked_fields"]}
        self.assertIn("qty", tracked_values)

    def test_no_field_appears_in_both_lists(self):
        result = get_field_options(source_doctype=CARRIER_DOCTYPE)
        tracked = {f["value"] for f in result["tracked_fields"]}
        balance = {f["value"] for f in result["balance_display_fields"]}
        overlap = tracked & balance
        self.assertEqual(overlap, set(), f"Fields appear in both lists: {overlap}")

    def test_read_only_fields_excluded_from_tracked(self):
        result = get_field_options(source_doctype=CARRIER_DOCTYPE)
        tracked_values = {f["value"] for f in result["tracked_fields"]}
        self.assertNotIn("balance", tracked_values)
        self.assertNotIn("credit", tracked_values)

    def test_editable_fields_excluded_from_balance_display(self):
        result = get_field_options(source_doctype=CARRIER_DOCTYPE)
        balance_values = {f["value"] for f in result["balance_display_fields"]}
        self.assertNotIn("qty", balance_values)

    def test_balance_display_fields_items_have_expected_shape(self):
        result = get_field_options(source_doctype=CARRIER_DOCTYPE)
        for item in result["balance_display_fields"]:
            self.assertIn("value", item)
            self.assertIn("label", item)

    def test_tracked_fields_items_have_expected_shape(self):
        result = get_field_options(source_doctype=CARRIER_DOCTYPE)
        for item in result["tracked_fields"]:
            self.assertIn("value", item)
            self.assertIn("label", item)
