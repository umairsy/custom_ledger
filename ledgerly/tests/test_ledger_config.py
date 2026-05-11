# Copyright (c) 2026, Ledgerly Contributors
# License: TBD. See license.txt

import unittest

import frappe

from ledgerly.ledgerly.doctype.ledger_config.ledger_config import get_field_options

# Test fixture DocType — created once for the whole suite so we don't rely on
# framework DocType field stability. Reused in PRs #4-#7 for engine tests.
FIXTURE_DOCTYPE = "Ledgerly Test Source"
FIXTURE_CHILD_DOCTYPE = "Ledgerly Test Source Line"


def _ensure_fixture_doctypes():
    """Create the test fixture DocTypes if they don't already exist.

    These are simple DocTypes with a known schema:
    - Ledgerly Test Source: tracked_value (Float), tracked_int (Int),
      category (Link -> DocType), notes (Data), lines (Table -> child)
    - Ledgerly Test Source Line: weight (Float), label (Data)

    Requires ``developer_mode = 1`` on the site, since creating DocTypes is a
    developer action. CI sets this in common_site_config.json. On a production
    Frappe Cloud site, tests will skip via the ``skipUnless`` guard below.
    """
    if not frappe.db.exists("DocType", FIXTURE_CHILD_DOCTYPE):
        child = frappe.get_doc(
            {
                "doctype": "DocType",
                "name": FIXTURE_CHILD_DOCTYPE,
                "module": "Ledgerly",
                "custom": 1,
                "istable": 1,
                "fields": [
                    {"fieldname": "weight", "fieldtype": "Float", "label": "Weight"},
                    {"fieldname": "label", "fieldtype": "Data", "label": "Label"},
                ],
                "permissions": [],
            }
        )
        child.insert(ignore_permissions=True)

    if not frappe.db.exists("DocType", FIXTURE_DOCTYPE):
        parent = frappe.get_doc(
            {
                "doctype": "DocType",
                "name": FIXTURE_DOCTYPE,
                "module": "Ledgerly",
                "custom": 1,
                "autoname": "hash",
                "fields": [
                    {
                        "fieldname": "tracked_value",
                        "fieldtype": "Float",
                        "label": "Tracked Value",
                    },
                    {
                        "fieldname": "tracked_int",
                        "fieldtype": "Int",
                        "label": "Tracked Int",
                    },
                    {
                        "fieldname": "category",
                        "fieldtype": "Link",
                        "options": "DocType",
                        "label": "Category",
                    },
                    {
                        "fieldname": "notes",
                        "fieldtype": "Data",
                        "label": "Notes",
                    },
                    {
                        "fieldname": "lines",
                        "fieldtype": "Table",
                        "options": FIXTURE_CHILD_DOCTYPE,
                        "label": "Lines",
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
        parent.insert(ignore_permissions=True)

    frappe.db.commit()


@unittest.skipUnless(
    frappe.conf.get("developer_mode"),
    "Ledger Config tests require developer_mode=1 to create fixture DocTypes.",
)
class TestLedgerConfig(unittest.TestCase):
    """Validation tests for the Ledger Config DocType."""

    @classmethod
    def setUpClass(cls):
        _ensure_fixture_doctypes()
        frappe.db.delete("Ledger Config", {"ledger_name": ["like", "Test %"]})
        frappe.db.commit()

    def tearDown(self):
        frappe.db.delete("Ledger Config", {"ledger_name": ["like", "Test %"]})
        frappe.db.commit()

    # ------------------------------------------------------------------
    # Schema / sanity
    # ------------------------------------------------------------------

    def test_doctype_exists(self):
        self.assertTrue(frappe.db.exists("DocType", "Ledger Config"))

    def test_not_submittable(self):
        meta = frappe.get_meta("Ledger Config")
        self.assertFalse(meta.is_submittable)

    def test_has_child_dimensions_table(self):
        meta = frappe.get_meta("Ledger Config")
        df = meta.get_field("dimensions")
        self.assertIsNotNone(df)
        self.assertEqual(df.fieldtype, "Table")
        self.assertEqual(df.options, "Ledger Dimension")

    # ------------------------------------------------------------------
    # Source DocType validation
    # ------------------------------------------------------------------

    def test_rejects_missing_source_doctype(self):
        doc = frappe.new_doc("Ledger Config")
        doc.ledger_name = "Test Missing Source"
        doc.source_doctype = "NonExistent DocType XYZ"
        doc.tracked_field = "x"
        with self.assertRaises(frappe.ValidationError):
            doc.insert()

    def test_rejects_child_table_as_source(self):
        """A child DocType (istable=1) cannot be the source."""
        doc = frappe.new_doc("Ledger Config")
        doc.ledger_name = "Test Child As Source"
        doc.source_doctype = FIXTURE_CHILD_DOCTYPE
        doc.tracked_field = "weight"
        with self.assertRaises(frappe.ValidationError):
            doc.insert()

    # ------------------------------------------------------------------
    # Tracked field validation
    # ------------------------------------------------------------------

    def test_rejects_non_numeric_tracked_field(self):
        doc = frappe.new_doc("Ledger Config")
        doc.ledger_name = "Test Non-Numeric Tracked"
        doc.source_doctype = FIXTURE_DOCTYPE
        doc.tracked_field = "notes"  # Data field
        with self.assertRaises(frappe.ValidationError):
            doc.insert()

    def test_rejects_nonexistent_tracked_field(self):
        doc = frappe.new_doc("Ledger Config")
        doc.ledger_name = "Test Missing Tracked"
        doc.source_doctype = FIXTURE_DOCTYPE
        doc.tracked_field = "definitely_not_a_field_xyz"
        with self.assertRaises(frappe.ValidationError):
            doc.insert()

    def test_accepts_float_tracked_field(self):
        doc = frappe.new_doc("Ledger Config")
        doc.ledger_name = "Test Float Tracked"
        doc.source_doctype = FIXTURE_DOCTYPE
        doc.tracked_field = "tracked_value"
        doc.insert()
        self.assertTrue(doc.name)

    def test_accepts_int_tracked_field(self):
        doc = frappe.new_doc("Ledger Config")
        doc.ledger_name = "Test Int Tracked"
        doc.source_doctype = FIXTURE_DOCTYPE
        doc.tracked_field = "tracked_int"
        doc.insert()
        self.assertTrue(doc.name)

    # ------------------------------------------------------------------
    # Child table support
    # ------------------------------------------------------------------

    def test_accepts_tracked_field_on_child_table(self):
        doc = frappe.new_doc("Ledger Config")
        doc.ledger_name = "Test Child Table Tracked"
        doc.source_doctype = FIXTURE_DOCTYPE
        doc.child_table_field = "lines"
        doc.tracked_field = "weight"
        doc.insert()
        self.assertTrue(doc.name)

    def test_rejects_non_table_child_table_field(self):
        doc = frappe.new_doc("Ledger Config")
        doc.ledger_name = "Test Bad Child Table Field"
        doc.source_doctype = FIXTURE_DOCTYPE
        doc.child_table_field = "notes"  # Data, not Table
        doc.tracked_field = "weight"
        with self.assertRaises(frappe.ValidationError):
            doc.insert()

    # ------------------------------------------------------------------
    # Dimension validation
    # ------------------------------------------------------------------

    def test_rejects_non_link_dimension(self):
        doc = frappe.new_doc("Ledger Config")
        doc.ledger_name = "Test Bad Dimension"
        doc.source_doctype = FIXTURE_DOCTYPE
        doc.tracked_field = "tracked_value"
        doc.append("dimensions", {"dimension_fieldname": "notes"})  # Data, not Link
        with self.assertRaises(frappe.ValidationError):
            doc.insert()

    def test_rejects_duplicate_dimensions(self):
        doc = frappe.new_doc("Ledger Config")
        doc.ledger_name = "Test Duplicate Dimensions"
        doc.source_doctype = FIXTURE_DOCTYPE
        doc.tracked_field = "tracked_value"
        doc.append("dimensions", {"dimension_fieldname": "category"})
        doc.append("dimensions", {"dimension_fieldname": "category"})
        with self.assertRaises(frappe.ValidationError):
            doc.insert()

    def test_enriches_dimensions_on_save(self):
        doc = frappe.new_doc("Ledger Config")
        doc.ledger_name = "Test Enrichment"
        doc.source_doctype = FIXTURE_DOCTYPE
        doc.tracked_field = "tracked_value"
        doc.append("dimensions", {"dimension_fieldname": "category"})
        doc.insert()

        dim = doc.dimensions[0]
        self.assertEqual(dim.label, "Category")
        self.assertEqual(dim.link_doctype, "DocType")

    def test_enforces_max_dimensions(self):
        # Add a second Link field to the fixture for this test.
        meta = frappe.get_meta(FIXTURE_DOCTYPE)
        if not meta.get_field("secondary_category"):
            df = frappe.get_doc("DocType", FIXTURE_DOCTYPE)
            df.append(
                "fields",
                {
                    "fieldname": "secondary_category",
                    "fieldtype": "Link",
                    "options": "DocType",
                    "label": "Secondary Category",
                },
            )
            df.save(ignore_permissions=True)
            frappe.db.commit()
            frappe.clear_cache(doctype=FIXTURE_DOCTYPE)

        frappe.local.conf["ledgerly_max_dimensions"] = 1
        try:
            doc = frappe.new_doc("Ledger Config")
            doc.ledger_name = "Test Max Dims"
            doc.source_doctype = FIXTURE_DOCTYPE
            doc.tracked_field = "tracked_value"
            doc.append("dimensions", {"dimension_fieldname": "category"})
            doc.append("dimensions", {"dimension_fieldname": "secondary_category"})
            with self.assertRaises(frappe.ValidationError):
                doc.insert()
        finally:
            frappe.local.conf.pop("ledgerly_max_dimensions", None)

    # ------------------------------------------------------------------
    # Whitelisted API
    # ------------------------------------------------------------------

    def test_get_field_options_returns_expected_shape(self):
        result = get_field_options(source_doctype=FIXTURE_DOCTYPE)
        self.assertIn("tracked_fields", result)
        self.assertIn("child_table_fields", result)
        self.assertIn("dimension_fields", result)

        tracked_names = {f["value"] for f in result["tracked_fields"]}
        self.assertIn("tracked_value", tracked_names)
        self.assertIn("tracked_int", tracked_names)
        self.assertNotIn("notes", tracked_names)  # Data field excluded

        dim_names = {f["value"] for f in result["dimension_fields"]}
        self.assertIn("category", dim_names)
        self.assertNotIn("notes", dim_names)  # Data field excluded
        self.assertNotIn("tracked_value", dim_names)  # Float field excluded

        child_names = {f["value"] for f in result["child_table_fields"]}
        self.assertIn("lines", child_names)

    def test_get_field_options_with_child_table_filter(self):
        """When child_table_field is set, tracked fields come from the child meta."""
        result = get_field_options(
            source_doctype=FIXTURE_DOCTYPE, child_table_field="lines"
        )
        tracked_names = {f["value"] for f in result["tracked_fields"]}
        self.assertIn("weight", tracked_names)
        # The parent's tracked_value should NOT appear when child is selected.
        self.assertNotIn("tracked_value", tracked_names)

    def test_get_field_options_handles_missing_doctype(self):
        result = get_field_options(source_doctype="NonExistent XYZ")
        self.assertEqual(result["tracked_fields"], [])
        self.assertEqual(result["dimension_fields"], [])
