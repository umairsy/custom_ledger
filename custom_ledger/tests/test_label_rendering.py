# Copyright (c) 2026, Custom Ledger Contributors
# License: TBD. See license.txt

import unittest

import frappe

from custom_ledger.custom_ledger.doctype.ledger_config.ledger_config import (
    _disambiguate,
    get_field_options,
)
from custom_ledger.tests.test_ledger_config import FIXTURE_DOCTYPE, _ensure_fixture_doctypes


@unittest.skipUnless(
    frappe.conf.get("developer_mode"),
    "Label rendering tests require developer_mode=1 to access fixture DocTypes.",
)
class TestDisambiguate(unittest.TestCase):
    """Unit tests for the _disambiguate helper — no DB required."""

    def test_unique_labels_unchanged(self):
        items = [
            {"value": "alpha", "label": "Alpha"},
            {"value": "beta", "label": "Beta"},
        ]
        result = _disambiguate(items)
        self.assertEqual(result[0]["label"], "Alpha")
        self.assertEqual(result[1]["label"], "Beta")

    def test_duplicate_labels_get_fieldname_suffix(self):
        items = [
            {"value": "amount", "label": "Amount"},
            {"value": "total", "label": "Amount"},
        ]
        result = _disambiguate(items)
        self.assertEqual(result[0]["label"], "Amount (amount)")
        self.assertEqual(result[1]["label"], "Amount (total)")

    def test_values_preserved(self):
        items = [
            {"value": "field_a", "label": "X"},
            {"value": "field_b", "label": "X"},
        ]
        result = _disambiguate(items)
        self.assertEqual(result[0]["value"], "field_a")
        self.assertEqual(result[1]["value"], "field_b")

    def test_single_item_unchanged(self):
        items = [{"value": "qty", "label": "Quantity"}]
        result = _disambiguate(items)
        self.assertEqual(result[0]["label"], "Quantity")

    def test_empty_list(self):
        self.assertEqual(_disambiguate([]), [])

    def test_mixed_collision_and_unique(self):
        items = [
            {"value": "a", "label": "Name"},
            {"value": "b", "label": "Name"},
            {"value": "c", "label": "Unique"},
        ]
        result = _disambiguate(items)
        self.assertEqual(result[0]["label"], "Name (a)")
        self.assertEqual(result[1]["label"], "Name (b)")
        self.assertEqual(result[2]["label"], "Unique")


@unittest.skipUnless(
    frappe.conf.get("developer_mode"),
    "Label rendering tests require developer_mode=1 to access fixture DocTypes.",
)
class TestGetFieldOptionsLabels(unittest.TestCase):
    """Integration tests verifying get_field_options returns plain labels."""

    @classmethod
    def setUpClass(cls):
        _ensure_fixture_doctypes()

    def test_tracked_fields_label_has_no_fieldtype(self):
        result = get_field_options(FIXTURE_DOCTYPE)
        for f in result["tracked_fields"]:
            self.assertNotIn("(Float)", f["label"])
            self.assertNotIn("(Int)", f["label"])
            self.assertNotIn("(Currency)", f["label"])

    def test_tracked_fields_label_is_human_readable(self):
        result = get_field_options(FIXTURE_DOCTYPE)
        labels = [f["label"] for f in result["tracked_fields"]]
        # Fixture has "Tracked Value" and "Tracked Int" — labels, not raw fieldnames
        self.assertIn("Tracked Value", labels)
        self.assertIn("Tracked Int", labels)

    def test_posting_date_fields_label_has_no_fieldtype(self):
        result = get_field_options(FIXTURE_DOCTYPE)
        for f in result["posting_date_fields"]:
            self.assertNotIn("(Date)", f["label"])
            self.assertNotIn("(Datetime)", f["label"])

    def test_posting_time_fields_label_has_no_fieldtype(self):
        result = get_field_options(FIXTURE_DOCTYPE)
        for f in result["posting_time_fields"]:
            self.assertNotIn("(Time)", f["label"])

    def test_narration_fields_label_has_no_fieldtype(self):
        result = get_field_options(FIXTURE_DOCTYPE)
        for f in result["narration_fields"]:
            self.assertNotIn("(Data)", f["label"])
            self.assertNotIn("(Small Text)", f["label"])

    def test_value_is_always_fieldname(self):
        result = get_field_options(FIXTURE_DOCTYPE)
        meta = frappe.get_meta(FIXTURE_DOCTYPE)
        for key in ("tracked_fields", "posting_date_fields", "posting_time_fields"):
            for f in result[key]:
                self.assertIsNotNone(
                    meta.get_field(f["value"]),
                    f"Value '{f['value']}' in {key} is not a valid fieldname",
                )
