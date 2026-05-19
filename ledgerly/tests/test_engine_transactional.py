# Copyright (c) 2026, Ledgerly Contributors
# License: TBD. See license.txt

import unittest
from datetime import date

import frappe
from frappe.utils import flt

from ledgerly.core.engine_transactional import (
    _FEEDER_CACHE_KEY,
    capture_cancel,
    capture_submit,
)

FEEDER_DOCTYPE = "Ledgerly Test Feeder"
CARRIER_DOCTYPE = "Ledgerly Test Carrier"


def _ensure_fixture_doctypes():
    """Create carrier and feeder fixture doctypes if they don't already exist."""
    if not frappe.db.exists("DocType", CARRIER_DOCTYPE):
        carrier = frappe.get_doc(
            {
                "doctype": "DocType",
                "name": CARRIER_DOCTYPE,
                "module": "Ledgerly",
                "custom": 1,
                "fields": [
                    {
                        "fieldname": "balance",
                        "fieldtype": "Float",
                        "label": "Balance",
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
        carrier.insert(ignore_permissions=True)

    if not frappe.db.exists("DocType", FEEDER_DOCTYPE):
        feeder = frappe.get_doc(
            {
                "doctype": "DocType",
                "name": FEEDER_DOCTYPE,
                "module": "Ledgerly",
                "custom": 1,
                "is_submittable": 1,
                "fields": [
                    {"fieldname": "amount", "fieldtype": "Float", "label": "Amount"},
                    {
                        "fieldname": "payment_date",
                        "fieldtype": "Date",
                        "label": "Payment Date",
                    },
                    {
                        "fieldname": "carrier",
                        "fieldtype": "Link",
                        "options": CARRIER_DOCTYPE,
                        "label": "Carrier",
                    },
                ],
                "permissions": [
                    {
                        "role": "System Manager",
                        "read": 1,
                        "write": 1,
                        "create": 1,
                        "delete": 1,
                        "submit": 1,
                        "cancel": 1,
                    }
                ],
            }
        )
        feeder.insert(ignore_permissions=True)

    frappe.db.commit()


def _make_config(name, direction="ADD", is_active=1):
    """Insert a Type 2 Ledger Config for the fixture doctypes and return it."""
    existing = frappe.db.exists("Ledger Config", {"ledger_name": name})
    if existing:
        return frappe.get_doc("Ledger Config", existing)

    config = frappe.get_doc(
        {
            "doctype": "Ledger Config",
            "ledger_name": name,
            "ledger_type": "Track balance from transactions",
            "balance_carrier_doctype": CARRIER_DOCTYPE,
            "balance_field": "balance",
            "is_active": is_active,
            "sources": [
                {
                    "source_doctype": FEEDER_DOCTYPE,
                    "source_field": "amount",
                    "direction": direction,
                    "carrier_link_field": "carrier",
                    "posting_date_field": "payment_date",
                    "is_active": 1,
                }
            ],
        }
    )
    config.insert(ignore_permissions=True)
    frappe.cache().delete_value(_FEEDER_CACHE_KEY)
    return config


def _make_carrier():
    """Insert a carrier doc and return it."""
    doc = frappe.get_doc({"doctype": CARRIER_DOCTYPE})
    doc.insert(ignore_permissions=True)
    return doc


def _make_feeder(carrier_name, amount=100.0):
    """Insert a feeder doc (without submitting) and return it."""
    doc = frappe.get_doc(
        {
            "doctype": FEEDER_DOCTYPE,
            "amount": amount,
            "payment_date": date.today().isoformat(),
            "carrier": carrier_name,
        }
    )
    doc.insert(ignore_permissions=True)
    return doc


def _get_entries(ledger_config_name, source_name):
    """ledger_config_name is the document name (PK), e.g. 'LDG-CFG-00001'."""
    return frappe.get_all(
        "Ledger Entry",
        filters={"ledger_config": ledger_config_name, "source_name": source_name, "docstatus": 1},
        fields=["name", "value", "delta", "balance", "is_reversal", "reverses"],
    )


def _carrier_balance(carrier_name):
    return flt(frappe.db.get_value(CARRIER_DOCTYPE, carrier_name, "balance"))


@unittest.skipUnless(
    frappe.conf.get("developer_mode"),
    "Transactional engine tests require developer_mode=1.",
)
class TestTransactionalEngine(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        _ensure_fixture_doctypes()

    def setUp(self):
        # Cancel then delete all Ledger Entries.
        for name in frappe.get_all("Ledger Entry", pluck="name"):
            entry = frappe.get_doc("Ledger Entry", name)
            if entry.docstatus == 1:
                entry.cancel()
            entry.delete(ignore_permissions=True)
        # Remove test Ledger Configs (raw delete to avoid hook side effects).
        frappe.db.delete("Ledger Config", {"ledger_name": ["like", "T2 %"]})
        # Remove all fixture feeder and carrier docs.
        frappe.db.delete(FEEDER_DOCTYPE)
        frappe.db.delete(CARRIER_DOCTYPE)
        # Clear feeder doctype cache so next test sees a fresh state.
        frappe.cache().delete_value(_FEEDER_CACHE_KEY)
        frappe.db.commit()

    # ------------------------------------------------------------------
    # Submit path — ADD direction
    # ------------------------------------------------------------------

    def test_submit_add_creates_entry_and_updates_balance(self):
        """ADD direction: one entry is created and carrier balance equals the source value."""
        config = _make_config("T2 Add")
        carrier = _make_carrier()
        feeder = _make_feeder(carrier.name, amount=150.0)

        capture_submit(feeder)

        entries = _get_entries(config.name, feeder.name)
        self.assertEqual(len(entries), 1)
        self.assertAlmostEqual(flt(entries[0].value), 150.0)
        self.assertAlmostEqual(flt(entries[0].delta), 150.0)
        self.assertAlmostEqual(_carrier_balance(carrier.name), 150.0)

    # ------------------------------------------------------------------
    # Submit path — DEDUCT direction
    # ------------------------------------------------------------------

    def test_submit_deduct_decreases_balance(self):
        """DEDUCT direction: delta is negative and carrier balance decreases accordingly."""
        config = _make_config("T2 Deduct", direction="DEDUCT")
        carrier = _make_carrier()
        feeder = _make_feeder(carrier.name, amount=75.0)

        capture_submit(feeder)

        entries = _get_entries(config.name, feeder.name)
        self.assertEqual(len(entries), 1)
        self.assertAlmostEqual(flt(entries[0].value), 75.0)
        self.assertAlmostEqual(flt(entries[0].delta), -75.0)
        self.assertAlmostEqual(_carrier_balance(carrier.name), -75.0)

    # ------------------------------------------------------------------
    # Submit idempotency
    # ------------------------------------------------------------------

    def test_submit_is_idempotent(self):
        """Calling capture_submit twice for the same doc creates only one entry."""
        config = _make_config("T2 Idempotent Submit")
        carrier = _make_carrier()
        feeder = _make_feeder(carrier.name, amount=200.0)

        capture_submit(feeder)
        capture_submit(feeder)

        entries = _get_entries(config.name, feeder.name)
        self.assertEqual(len(entries), 1)
        self.assertAlmostEqual(_carrier_balance(carrier.name), 200.0)

    # ------------------------------------------------------------------
    # Cancel path
    # ------------------------------------------------------------------

    def test_cancel_creates_reversal_and_restores_balance(self):
        """After submit + cancel, a reversal entry exists and the carrier balance is 0."""
        _make_config("T2 Cancel")
        carrier = _make_carrier()
        feeder = _make_feeder(carrier.name, amount=300.0)

        capture_submit(feeder)
        self.assertAlmostEqual(_carrier_balance(carrier.name), 300.0)

        capture_cancel(feeder)

        all_entries = frappe.get_all(
            "Ledger Entry",
            filters={"source_name": feeder.name, "docstatus": 1},
            fields=["name", "delta", "is_reversal"],
        )
        self.assertEqual(len(all_entries), 2)
        reversals = [e for e in all_entries if e.is_reversal]
        self.assertEqual(len(reversals), 1)
        self.assertAlmostEqual(flt(reversals[0].delta), -300.0)
        self.assertAlmostEqual(_carrier_balance(carrier.name), 0.0)

    # ------------------------------------------------------------------
    # Cancel idempotency
    # ------------------------------------------------------------------

    def test_cancel_is_idempotent(self):
        """Calling capture_cancel twice creates only one reversal entry."""
        _make_config("T2 Idempotent Cancel")
        carrier = _make_carrier()
        feeder = _make_feeder(carrier.name, amount=50.0)

        capture_submit(feeder)
        capture_cancel(feeder)
        capture_cancel(feeder)

        reversals = frappe.get_all(
            "Ledger Entry",
            filters={"source_name": feeder.name, "is_reversal": 1, "docstatus": 1},
            pluck="name",
        )
        self.assertEqual(len(reversals), 1)

    # ------------------------------------------------------------------
    # Non-feeder doctype
    # ------------------------------------------------------------------

    def test_non_feeder_doctype_is_skipped(self):
        """capture_submit on a doctype not in any active config creates no entries."""
        _make_config("T2 Non Feeder")

        fake_doc = frappe._dict(doctype="User", name="Administrator")
        capture_submit(fake_doc)

        entries = frappe.get_all(
            "Ledger Entry", filters={"source_doctype": "User"}, pluck="name"
        )
        self.assertEqual(len(entries), 0)

    # ------------------------------------------------------------------
    # Zero-value source field
    # ------------------------------------------------------------------

    def test_zero_value_creates_no_entry(self):
        """A feeder doc with amount=0 produces no Ledger Entry."""
        config = _make_config("T2 Zero Value")
        carrier = _make_carrier()
        feeder = _make_feeder(carrier.name, amount=0.0)

        capture_submit(feeder)

        entries = _get_entries(config.name, feeder.name)
        self.assertEqual(len(entries), 0)
        self.assertAlmostEqual(_carrier_balance(carrier.name), 0.0)

    # ------------------------------------------------------------------
    # Missing carrier link value
    # ------------------------------------------------------------------

    def test_missing_carrier_link_creates_no_entry(self):
        """A feeder doc with no carrier value logs an error and creates no entry."""
        config = _make_config("T2 No Carrier")
        feeder = _make_feeder(carrier_name=None, amount=100.0)
        feeder.carrier = None  # ensure in-memory value is also unset

        capture_submit(feeder)

        entries = _get_entries(config.name, feeder.name)
        self.assertEqual(len(entries), 0)

    # ------------------------------------------------------------------
    # Multiple feeders accumulate balance
    # ------------------------------------------------------------------

    def test_multiple_feeders_accumulate_carrier_balance(self):
        """Balance after two ADD submissions equals the sum of both source values."""
        _make_config("T2 Multi Feeder")
        carrier = _make_carrier()
        feeder1 = _make_feeder(carrier.name, amount=100.0)
        feeder2 = _make_feeder(carrier.name, amount=250.0)

        capture_submit(feeder1)
        capture_submit(feeder2)

        self.assertAlmostEqual(_carrier_balance(carrier.name), 350.0)
