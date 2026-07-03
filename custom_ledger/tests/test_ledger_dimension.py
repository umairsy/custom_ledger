# Copyright (c) 2026, Custom Ledger Contributors
# License: TBD. See license.txt

import unittest

import frappe


class TestLedgerDimension(unittest.TestCase):
    """Schema and validation tests for the Ledger Dimension child DocType."""

    def test_doctype_exists(self):
        """Ledger Dimension should exist after migration."""
        self.assertTrue(frappe.db.exists("DocType", "Ledger Dimension"))

    def test_is_child_table(self):
        """Ledger Dimension must be marked as a child table (istable=1)."""
        meta = frappe.get_meta("Ledger Dimension")
        self.assertTrue(meta.istable, "Ledger Dimension should be a child table")

    def test_not_submittable(self):
        """Child rows must not be submittable."""
        meta = frappe.get_meta("Ledger Dimension")
        self.assertFalse(meta.is_submittable)

    def test_required_fields_present(self):
        """All four declared fields must exist on the meta."""
        meta = frappe.get_meta("Ledger Dimension")
        fieldnames = {df.fieldname for df in meta.fields}
        for expected in ("dimension_fieldname", "label", "link_doctype", "is_mandatory_filter"):
            self.assertIn(expected, fieldnames, f"Missing field: {expected}")

    def test_dimension_fieldname_is_mandatory(self):
        """dimension_fieldname must be reqd=1."""
        meta = frappe.get_meta("Ledger Dimension")
        df = meta.get_field("dimension_fieldname")
        self.assertTrue(df.reqd)

    def test_label_is_readonly(self):
        """label must be read-only (auto-populated by parent)."""
        meta = frappe.get_meta("Ledger Dimension")
        df = meta.get_field("label")
        self.assertTrue(df.read_only)

    def test_link_doctype_is_readonly(self):
        """link_doctype must be read-only (auto-populated by parent)."""
        meta = frappe.get_meta("Ledger Dimension")
        df = meta.get_field("link_doctype")
        self.assertTrue(df.read_only)

    def test_validate_rejects_fieldname_with_spaces(self):
        """Dimension fieldname containing a space must raise."""
        # Child rows can't be inserted independently; instantiate without insert.
        doc = frappe.new_doc("Ledger Dimension")
        doc.dimension_fieldname = "item group"
        with self.assertRaises(frappe.ValidationError):
            doc.validate()

    def test_validate_strips_whitespace(self):
        """Leading/trailing whitespace should be stripped from the fieldname."""
        doc = frappe.new_doc("Ledger Dimension")
        doc.dimension_fieldname = "  item_group  "
        doc.validate()
        self.assertEqual(doc.dimension_fieldname, "item_group")
