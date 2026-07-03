# Copyright (c) 2026, Custom Ledger Contributors
# License: TBD. See license.txt

import unittest
from unittest.mock import patch

import frappe

from custom_ledger.core.field_protection import _find_blocking_configs, block_if_referenced


class _FakeCustomField:
    def __init__(self, dt, fieldname):
        self.dt = dt
        self.fieldname = fieldname


class TestBlockIfReferenced(unittest.TestCase):
    """Unit tests for block_if_referenced — mocked at _find_blocking_configs."""

    def test_allows_delete_when_no_blocking_configs(self):
        with patch(
            "custom_ledger.core.field_protection._find_blocking_configs", return_value=[]
        ):
            doc = _FakeCustomField("SomeDocType", "some_field")
            block_if_referenced(doc)  # must not raise

    def test_throws_when_blocking_configs_exist(self):
        with patch(
            "custom_ledger.core.field_protection._find_blocking_configs",
            return_value=["LDG-CFG-00001"],
        ):
            doc = _FakeCustomField("SomeDocType", "some_field")
            with self.assertRaises(frappe.ValidationError):
                block_if_referenced(doc)

    def test_error_message_contains_config_names(self):
        with patch(
            "custom_ledger.core.field_protection._find_blocking_configs",
            return_value=["LDG-CFG-00001", "LDG-CFG-00002"],
        ):
            doc = _FakeCustomField("Invoice", "amount")
            try:
                block_if_referenced(doc)
                self.fail("Expected ValidationError")
            except frappe.ValidationError as e:
                self.assertIn("LDG-CFG-00001", str(e))
                self.assertIn("LDG-CFG-00002", str(e))

    def test_error_message_contains_doctype_and_fieldname(self):
        with patch(
            "custom_ledger.core.field_protection._find_blocking_configs",
            return_value=["LDG-CFG-99999"],
        ):
            doc = _FakeCustomField("Invoice", "custom_amount")
            try:
                block_if_referenced(doc)
                self.fail("Expected ValidationError")
            except frappe.ValidationError as e:
                self.assertIn("Invoice", str(e))
                self.assertIn("custom_amount", str(e))

    def test_multiple_blocking_configs_all_mentioned(self):
        configs = ["LDG-CFG-A", "LDG-CFG-B", "LDG-CFG-C"]
        with patch(
            "custom_ledger.core.field_protection._find_blocking_configs",
            return_value=configs,
        ):
            doc = _FakeCustomField("SalesOrder", "custom_ref")
            try:
                block_if_referenced(doc)
                self.fail("Expected ValidationError")
            except frappe.ValidationError as e:
                for cfg in configs:
                    self.assertIn(cfg, str(e))


@unittest.skipUnless(
    frappe.conf.get("developer_mode"),
    "DB-level field protection tests require developer_mode=1.",
)
class TestFindBlockingConfigsDB(unittest.TestCase):
    """Integration tests for _find_blocking_configs against the live DB."""

    def test_returns_empty_for_unknown_doctype(self):
        result = _find_blocking_configs("NonExistentDocTypeXYZ", "some_field")
        self.assertEqual(result, [])

    def test_returns_empty_for_unknown_field_on_existing_doctype(self):
        # "User" is always present but has no Custom Ledger tracking.
        result = _find_blocking_configs("User", "nonexistent_custom_field_xyz")
        self.assertEqual(result, [])
