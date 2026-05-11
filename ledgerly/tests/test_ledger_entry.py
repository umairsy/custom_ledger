# Copyright (c) 2026, Ledgerly Contributors
# License: TBD. See license.txt

import unittest

import frappe
from frappe.utils import get_datetime

# Reuse the fixture DocTypes created by the Ledger Config tests.
from ledgerly.tests.test_ledger_config import _ensure_fixture_doctypes, FIXTURE_DOCTYPE


def _make_source_doc():
    """Create one row in the fixture DocType to point at."""
    doc = frappe.get_doc(
        {
            "doctype": FIXTURE_DOCTYPE,
            "tracked_value": 100.0,
            "tracked_int": 100,
            "notes": "test fixture row",
        }
    )
    doc.insert(ignore_permissions=True)
    return doc


def _make_ledger_config():
    """Create a minimal Ledger Config to point Ledger Entries at."""
    name = "Test Entry Config"
    existing = frappe.db.exists("Ledger Config", {"ledger_name": name})
    if existing:
        return frappe.get_doc("Ledger Config", existing)

    config = frappe.get_doc(
        {
            "doctype": "Ledger Config",
            "ledger_name": name,
            "source_doctype": FIXTURE_DOCTYPE,
            "value_source_mode": "Field on document",
            "tracked_field": "tracked_value",
            "posting_date_source": "Document modification time",
        }
    )
    config.insert(ignore_permissions=True)
    return config


def _base_entry(config_name: str, source_name: str, **overrides) -> dict:
    """Returns a minimal valid Ledger Entry dict for tests."""
    base = {
        "doctype": "Ledger Entry",
        "ledger_config": config_name,
        "source_doctype": FIXTURE_DOCTYPE,
        "source_name": source_name,
        "posting_date": "2026-05-01",
        "posting_time": "10:30:00",
        "value": 100.0,
        "delta": 0.0,
        "balance": 100.0,
    }
    base.update(overrides)
    return base


@unittest.skipUnless(
    frappe.conf.get("developer_mode"),
    "Ledger Entry tests require developer_mode=1 to create fixture DocTypes.",
)
class TestLedgerEntry(unittest.TestCase):
    """Schema and lifecycle tests for the Ledger Entry DocType."""

    @classmethod
    def setUpClass(cls):
        _ensure_fixture_doctypes()
        # Persistent fixture: one config + one source doc.
        cls.config = _make_ledger_config()
        cls.source = _make_source_doc()

    def setUp(self):
        # Cancel + delete any leftover entries from prior tests.
        for name in frappe.get_all(
            "Ledger Entry",
            filters={"ledger_config": self.config.name},
            pluck="name",
        ):
            doc = frappe.get_doc("Ledger Entry", name)
            if doc.docstatus == 1:
                doc.cancel()
            doc.delete(ignore_permissions=True)
        frappe.db.commit()

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def test_doctype_exists(self):
        self.assertTrue(frappe.db.exists("DocType", "Ledger Entry"))

    def test_is_submittable(self):
        meta = frappe.get_meta("Ledger Entry")
        self.assertTrue(meta.is_submittable)

    def test_has_five_dimension_columns(self):
        meta = frappe.get_meta("Ledger Entry")
        for i in range(1, 6):
            self.assertIsNotNone(meta.get_field(f"dim_{i}"), f"Missing dim_{i}")
            self.assertIsNotNone(
                meta.get_field(f"dim_{i}_doctype"), f"Missing dim_{i}_doctype"
            )

    def test_has_required_fields(self):
        meta = frappe.get_meta("Ledger Entry")
        for fieldname in (
            "ledger_config",
            "source_doctype",
            "source_name",
            "posting_date",
            "posting_time",
            "posting_datetime",
            "value",
            "delta",
            "balance",
            "change_signature",
        ):
            self.assertIsNotNone(meta.get_field(fieldname), f"Missing {fieldname}")

    # ------------------------------------------------------------------
    # posting_datetime composition
    # ------------------------------------------------------------------

    def test_composes_posting_datetime_from_date_and_time(self):
        entry = frappe.get_doc(
            _base_entry(
                self.config.name,
                self.source.name,
                posting_date="2026-05-01",
                posting_time="14:30:45",
            )
        )
        entry.insert()
        expected = get_datetime("2026-05-01 14:30:45")
        self.assertEqual(entry.posting_datetime, expected)

    def test_defaults_posting_time_to_midnight_if_missing(self):
        # Posting_time is reqd in the JSON schema, but the controller defaults it
        # to "00:00:00" if missing. Bypass schema validation by injecting at low level.
        entry = frappe.new_doc("Ledger Entry")
        entry.update(_base_entry(self.config.name, self.source.name))
        entry.posting_time = None  # Force controller fallback
        entry.insert()
        self.assertEqual(str(entry.posting_time), "00:00:00")
        self.assertEqual(entry.posting_datetime.hour, 0)
        self.assertEqual(entry.posting_datetime.minute, 0)

    # ------------------------------------------------------------------
    # change_signature
    # ------------------------------------------------------------------

    def test_computes_change_signature(self):
        entry = frappe.get_doc(_base_entry(self.config.name, self.source.name))
        entry.insert()
        self.assertTrue(entry.change_signature)
        self.assertEqual(len(entry.change_signature), 32)  # Truncated SHA256

    def test_signature_is_stable_for_same_inputs(self):
        e1 = frappe.get_doc(_base_entry(self.config.name, self.source.name))
        e1.insert()
        sig1 = e1.change_signature

        e2 = frappe.get_doc(_base_entry(self.config.name, self.source.name))
        e2.insert()
        # Same source, same datetime, same value -> same signature.
        self.assertEqual(e2.change_signature, sig1)

    def test_signature_differs_for_different_value(self):
        e1 = frappe.get_doc(_base_entry(self.config.name, self.source.name, value=100.0))
        e1.insert()

        e2 = frappe.get_doc(_base_entry(self.config.name, self.source.name, value=101.0))
        e2.insert()
        self.assertNotEqual(e1.change_signature, e2.change_signature)

    # ------------------------------------------------------------------
    # Submit / cancel lifecycle
    # ------------------------------------------------------------------

    def test_can_submit_entry(self):
        entry = frappe.get_doc(_base_entry(self.config.name, self.source.name))
        entry.insert()
        entry.submit()
        self.assertEqual(entry.docstatus, 1)

    def test_can_cancel_submitted_entry(self):
        entry = frappe.get_doc(_base_entry(self.config.name, self.source.name))
        entry.insert()
        entry.submit()
        entry.cancel()
        self.assertEqual(entry.docstatus, 2)

    def test_cannot_delete_submitted_entry(self):
        entry = frappe.get_doc(_base_entry(self.config.name, self.source.name))
        entry.insert()
        entry.submit()
        with self.assertRaises(frappe.ValidationError):
            entry.delete()

    def test_can_delete_draft_entry(self):
        """Drafts (docstatus=0) should be deletable for cleanup."""
        entry = frappe.get_doc(_base_entry(self.config.name, self.source.name))
        entry.insert()
        # Not submitted.
        entry_name = entry.name
        entry.delete(ignore_permissions=True)
        self.assertFalse(frappe.db.exists("Ledger Entry", entry_name))

    # ------------------------------------------------------------------
    # Indexes (smoke check: indexed fields should be marked in meta)
    # ------------------------------------------------------------------

    def test_critical_fields_are_indexed(self):
        meta = frappe.get_meta("Ledger Entry")
        for fieldname in ("ledger_config", "source_doctype", "source_name", "posting_datetime"):
            df = meta.get_field(fieldname)
            self.assertTrue(
                df.search_index,
                f"Field {fieldname} should have search_index=1 for query performance",
            )
