# Copyright (c) 2026, Custom Ledger Contributors
# License: TBD. See license.txt

import unittest
from datetime import datetime

import frappe
from frappe.utils import get_datetime

from custom_ledger.custom_ledger.doctype.ledger_config.ledger_config import (
    get_field_options,
    get_field_type,
)

FIXTURE_DOCTYPE = "Custom Ledger Test Source"
FIXTURE_CHILD_DOCTYPE = "Custom Ledger Test Source Line"


def _ensure_fixture_doctypes():
    """Create fixture DocTypes if they don't already exist.

    Schema:
    - Custom Ledger Test Source: tracked_value (Float), tracked_int (Int),
      category (Link -> DocType), notes (Data), lines (Table -> child),
      measurement_date (Date), measurement_datetime (Datetime),
      measurement_time (Time).
    - Custom Ledger Test Source Line: weight (Float), label (Data).

    Requires ``developer_mode = 1`` on the site (CI sets this).
    """
    if not frappe.db.exists("DocType", FIXTURE_CHILD_DOCTYPE):
        child = frappe.get_doc(
            {
                "doctype": "DocType",
                "name": FIXTURE_CHILD_DOCTYPE,
                "module": "Custom Ledger",
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
                "module": "Custom Ledger",
                "custom": 1,
                "autoname": "hash",
                "fields": [
                    {"fieldname": "tracked_value", "fieldtype": "Float", "label": "Tracked Value"},
                    {"fieldname": "tracked_int", "fieldtype": "Int", "label": "Tracked Int"},
                    {
                        "fieldname": "category",
                        "fieldtype": "Link",
                        "options": "DocType",
                        "label": "Category",
                    },
                    {"fieldname": "notes", "fieldtype": "Data", "label": "Notes"},
                    {
                        "fieldname": "lines",
                        "fieldtype": "Table",
                        "options": FIXTURE_CHILD_DOCTYPE,
                        "label": "Lines",
                    },
                    {"fieldname": "measurement_date", "fieldtype": "Date", "label": "Measurement Date"},
                    {
                        "fieldname": "measurement_datetime",
                        "fieldtype": "Datetime",
                        "label": "Measurement Datetime",
                    },
                    {"fieldname": "measurement_time", "fieldtype": "Time", "label": "Measurement Time"},
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


def _base_config(name: str) -> dict:
    """Returns a minimal valid Ledger Config dict for the fixture DocType."""
    return {
        "doctype": "Ledger Config",
        "ledger_name": name,
        "source_doctype": FIXTURE_DOCTYPE,
        "value_source_mode": "Field on document",
        "tracked_field": "tracked_value",
        "posting_date_source": "Document modification time",
    }


@unittest.skipUnless(
    frappe.conf.get("developer_mode"),
    "Ledger Config tests require developer_mode=1 to create fixture DocTypes.",
)
class TestLedgerConfig(unittest.TestCase):
    """Validation tests for Ledger Config."""

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

    def test_has_new_posting_fields(self):
        meta = frappe.get_meta("Ledger Config")
        for fieldname in ("posting_date_source", "posting_date_field", "posting_time_field",
                          "value_source_mode"):
            self.assertIsNotNone(meta.get_field(fieldname), f"Missing field: {fieldname}")

    # ------------------------------------------------------------------
    # Source validation (carry-over from PR #3)
    # ------------------------------------------------------------------

    def test_rejects_missing_source_doctype(self):
        doc = frappe.get_doc(
            {
                **_base_config("Test Missing Source"),
                "source_doctype": "NonExistent DocType XYZ",
            }
        )
        with self.assertRaises(frappe.ValidationError):
            doc.insert()

    def test_rejects_child_table_as_source(self):
        doc = frappe.get_doc(
            {
                **_base_config("Test Child Source"),
                "source_doctype": FIXTURE_CHILD_DOCTYPE,
                "tracked_field": "weight",
            }
        )
        with self.assertRaises(frappe.ValidationError):
            doc.insert()

    # ------------------------------------------------------------------
    # value_source_mode
    # ------------------------------------------------------------------

    def test_accepts_field_on_document_mode(self):
        doc = frappe.get_doc(_base_config("Test Field Mode"))
        doc.insert()
        self.assertTrue(doc.name)

    def test_accepts_sum_across_child_mode(self):
        doc = frappe.get_doc(
            {
                **_base_config("Test Child Mode"),
                "value_source_mode": "Sum across child rows",
                "child_table_field": "lines",
                "tracked_field": "weight",
            }
        )
        doc.insert()
        self.assertTrue(doc.name)

    def test_rejects_child_mode_without_child_table_field(self):
        doc = frappe.get_doc(
            {
                **_base_config("Test Child No Field"),
                "value_source_mode": "Sum across child rows",
                "tracked_field": "weight",
            }
        )
        with self.assertRaises(frappe.ValidationError):
            doc.insert()

    def test_field_mode_clears_stale_child_table_field(self):
        """If user picks child mode then switches back, child_table_field should clear on save."""
        doc = frappe.get_doc(
            {
                **_base_config("Test Mode Switch"),
                "value_source_mode": "Field on document",
                "child_table_field": "lines",  # Stale value from prior mode
            }
        )
        doc.insert()
        self.assertIsNone(doc.child_table_field)

    # ------------------------------------------------------------------
    # tracked_field validation
    # ------------------------------------------------------------------

    def test_rejects_non_numeric_tracked_field(self):
        doc = frappe.get_doc({**_base_config("Test Bad Tracked"), "tracked_field": "notes"})
        with self.assertRaises(frappe.ValidationError):
            doc.insert()

    def test_accepts_int_tracked_field(self):
        doc = frappe.get_doc({**_base_config("Test Int Tracked"), "tracked_field": "tracked_int"})
        doc.insert()
        self.assertTrue(doc.name)

    # ------------------------------------------------------------------
    # Posting date validation (NEW IN PR #3.5)
    # ------------------------------------------------------------------

    def test_rejects_missing_posting_date_source(self):
        doc = frappe.get_doc(
            {**_base_config("Test No Posting Source"), "posting_date_source": None}
        )
        with self.assertRaises(frappe.ValidationError):
            doc.insert()

    def test_rejects_invalid_posting_date_source(self):
        doc = frappe.get_doc(
            {**_base_config("Test Bad Posting Source"), "posting_date_source": "Made up source"}
        )
        with self.assertRaises(frappe.ValidationError):
            doc.insert()

    def test_field_source_requires_posting_date_field(self):
        doc = frappe.get_doc(
            {
                **_base_config("Test Field Source No Field"),
                "posting_date_source": "Field on source DocType",
            }
        )
        with self.assertRaises(frappe.ValidationError):
            doc.insert()

    def test_accepts_date_posting_field(self):
        doc = frappe.get_doc(
            {
                **_base_config("Test Date Posting"),
                "posting_date_source": "Field on source DocType",
                "posting_date_field": "measurement_date",
            }
        )
        doc.insert()
        self.assertTrue(doc.name)

    def test_accepts_datetime_posting_field(self):
        doc = frappe.get_doc(
            {
                **_base_config("Test DT Posting"),
                "posting_date_source": "Field on source DocType",
                "posting_date_field": "measurement_datetime",
            }
        )
        doc.insert()
        self.assertTrue(doc.name)

    def test_rejects_non_date_posting_field(self):
        doc = frappe.get_doc(
            {
                **_base_config("Test Bad Posting Field"),
                "posting_date_source": "Field on source DocType",
                "posting_date_field": "notes",  # Data, not Date/Datetime
            }
        )
        with self.assertRaises(frappe.ValidationError):
            doc.insert()

    def test_accepts_time_field_alongside_date(self):
        doc = frappe.get_doc(
            {
                **_base_config("Test Date+Time"),
                "posting_date_source": "Field on source DocType",
                "posting_date_field": "measurement_date",
                "posting_time_field": "measurement_time",
            }
        )
        doc.insert()
        self.assertTrue(doc.name)

    def test_rejects_time_field_with_datetime_date(self):
        """If date field is already a Datetime, a separate time field is redundant."""
        doc = frappe.get_doc(
            {
                **_base_config("Test Redundant Time"),
                "posting_date_source": "Field on source DocType",
                "posting_date_field": "measurement_datetime",
                "posting_time_field": "measurement_time",
            }
        )
        with self.assertRaises(frappe.ValidationError):
            doc.insert()

    def test_rejects_non_time_posting_time_field(self):
        doc = frappe.get_doc(
            {
                **_base_config("Test Bad Time Field"),
                "posting_date_source": "Field on source DocType",
                "posting_date_field": "measurement_date",
                "posting_time_field": "notes",  # Data, not Time
            }
        )
        with self.assertRaises(frappe.ValidationError):
            doc.insert()

    def test_modification_time_source_clears_stale_fields(self):
        """Switching back to modification time should clear field selections on save."""
        doc = frappe.get_doc(
            {
                **_base_config("Test Posting Clear"),
                "posting_date_source": "Document modification time",
                "posting_date_field": "measurement_date",  # Stale value
                "posting_time_field": "measurement_time",  # Stale value
            }
        )
        doc.insert()
        self.assertIsNone(doc.posting_date_field)
        self.assertIsNone(doc.posting_time_field)

    # ------------------------------------------------------------------
    # resolve_posting_datetime helper (NEW IN PR #3.5)
    # ------------------------------------------------------------------

    def test_resolve_posting_datetime_modification_mode(self):
        config = frappe.get_doc(_base_config("Test Resolve Mod"))
        config.insert()

        # Build a faux source doc with a modified timestamp.
        fake_doc = frappe._dict(
            doctype=FIXTURE_DOCTYPE,
            name="FAKE-1",
            modified="2026-04-27 10:30:00",
        )
        result = config.resolve_posting_datetime(fake_doc)
        self.assertEqual(result, get_datetime("2026-04-27 10:30:00"))

    def test_resolve_posting_datetime_field_mode_datetime(self):
        config = frappe.get_doc(
            {
                **_base_config("Test Resolve DT"),
                "posting_date_source": "Field on source DocType",
                "posting_date_field": "measurement_datetime",
            }
        )
        config.insert()

        fake_doc = frappe._dict(
            doctype=FIXTURE_DOCTYPE,
            name="FAKE-2",
            measurement_datetime="2026-04-28 14:00:00",
        )
        result = config.resolve_posting_datetime(fake_doc)
        self.assertEqual(result, get_datetime("2026-04-28 14:00:00"))

    def test_resolve_posting_datetime_field_mode_date_only(self):
        """Date-only posting field should produce 00:00:00 time."""
        config = frappe.get_doc(
            {
                **_base_config("Test Resolve Date"),
                "posting_date_source": "Field on source DocType",
                "posting_date_field": "measurement_date",
            }
        )
        config.insert()

        fake_doc = frappe._dict(
            doctype=FIXTURE_DOCTYPE,
            name="FAKE-3",
            measurement_date="2026-04-29",
        )
        result = config.resolve_posting_datetime(fake_doc)
        # get_datetime("2026-04-29") returns 2026-04-29 00:00:00.
        self.assertEqual(result.year, 2026)
        self.assertEqual(result.month, 4)
        self.assertEqual(result.day, 29)
        self.assertEqual(result.hour, 0)

    def test_resolve_posting_datetime_field_mode_date_plus_time(self):
        config = frappe.get_doc(
            {
                **_base_config("Test Resolve Date Plus Time"),
                "posting_date_source": "Field on source DocType",
                "posting_date_field": "measurement_date",
                "posting_time_field": "measurement_time",
            }
        )
        config.insert()

        fake_doc = frappe._dict(
            doctype=FIXTURE_DOCTYPE,
            name="FAKE-4",
            measurement_date="2026-04-30",
            measurement_time="09:15:00",
        )
        result = config.resolve_posting_datetime(fake_doc)
        self.assertEqual(result.year, 2026)
        self.assertEqual(result.month, 4)
        self.assertEqual(result.day, 30)
        self.assertEqual(result.hour, 9)
        self.assertEqual(result.minute, 15)

    def test_resolve_posting_datetime_raises_on_empty_field(self):
        """If the configured field is empty on the source doc, raise."""
        config = frappe.get_doc(
            {
                **_base_config("Test Empty Field"),
                "posting_date_source": "Field on source DocType",
                "posting_date_field": "measurement_date",
            }
        )
        config.insert()

        fake_doc = frappe._dict(
            doctype=FIXTURE_DOCTYPE, name="FAKE-5", measurement_date=None
        )
        with self.assertRaises(frappe.ValidationError):
            config.resolve_posting_datetime(fake_doc)

    # ------------------------------------------------------------------
    # Dimensions (carry-over)
    # ------------------------------------------------------------------

    def test_enriches_dimensions_on_save(self):
        doc = frappe.get_doc(_base_config("Test Enrichment"))
        doc.append("dimensions", {"dimension_fieldname": "category"})
        doc.insert()

        dim = doc.dimensions[0]
        self.assertEqual(dim.label, "Category")
        self.assertEqual(dim.link_doctype, "DocType")

    def test_rejects_non_link_dimension(self):
        doc = frappe.get_doc(_base_config("Test Bad Dim"))
        doc.append("dimensions", {"dimension_fieldname": "notes"})
        with self.assertRaises(frappe.ValidationError):
            doc.insert()

    # ------------------------------------------------------------------
    # Whitelisted API
    # ------------------------------------------------------------------

    def test_get_field_options_returns_new_lists(self):
        result = get_field_options(source_doctype=FIXTURE_DOCTYPE)
        self.assertIn("posting_date_fields", result)
        self.assertIn("posting_time_fields", result)

        date_names = {f["value"] for f in result["posting_date_fields"]}
        self.assertIn("measurement_date", date_names)
        self.assertIn("measurement_datetime", date_names)

        time_names = {f["value"] for f in result["posting_time_fields"]}
        self.assertIn("measurement_time", time_names)

    # ------------------------------------------------------------------
    # get_field_type helper (NEW IN PR #4.5)
    # ------------------------------------------------------------------

    def test_get_field_type_returns_datetime(self):
        self.assertEqual(
            get_field_type(source_doctype=FIXTURE_DOCTYPE, fieldname="measurement_datetime"),
            "Datetime",
        )

    def test_get_field_type_returns_date(self):
        self.assertEqual(
            get_field_type(source_doctype=FIXTURE_DOCTYPE, fieldname="measurement_date"),
            "Date",
        )

    def test_get_field_type_returns_none_for_missing_field(self):
        self.assertIsNone(
            get_field_type(source_doctype=FIXTURE_DOCTYPE, fieldname="does_not_exist_xyz")
        )

    def test_get_field_type_returns_none_for_missing_doctype(self):
        self.assertIsNone(
            get_field_type(source_doctype="NonExistent XYZ", fieldname="anything")
        )

    # ------------------------------------------------------------------
    # Time-fallback contract (NEW IN PR #4.5)
    # ------------------------------------------------------------------

    def test_resolve_posting_datetime_zero_microseconds(self):
        """posting_datetime must always have microsecond=0 for stable equality."""
        config = frappe.get_doc(
            {
                **_base_config("Test Microsec Zero"),
                "posting_date_source": "Field on source DocType",
                "posting_date_field": "measurement_datetime",
            }
        )
        config.insert()

        # Datetime with non-zero microseconds — should be stripped.
        fake_doc = frappe._dict(
            doctype=FIXTURE_DOCTYPE,
            name="FAKE-MS",
            measurement_datetime="2026-04-28 14:00:00.123456",
        )
        result = config.resolve_posting_datetime(fake_doc)
        self.assertEqual(result.microsecond, 0)

    def test_resolve_posting_datetime_empty_time_falls_back_to_midnight(self):
        """If posting_time_field is configured but empty on the source, use 00:00:00."""
        config = frappe.get_doc(
            {
                **_base_config("Test Empty Time Fallback"),
                "posting_date_source": "Field on source DocType",
                "posting_date_field": "measurement_date",
                "posting_time_field": "measurement_time",
            }
        )
        config.insert()

        fake_doc = frappe._dict(
            doctype=FIXTURE_DOCTYPE,
            name="FAKE-EMPTY-TIME",
            measurement_date="2026-05-01",
            measurement_time=None,  # Empty time on the source doc
        )
        result = config.resolve_posting_datetime(fake_doc)
        self.assertEqual(result.hour, 0)
        self.assertEqual(result.minute, 0)
        self.assertEqual(result.second, 0)
