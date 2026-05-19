# Copyright (c) 2026, Ledgerly Contributors
# License: TBD. See license.txt

import unittest
from unittest.mock import patch

import frappe

from ledgerly.core.balance_recompute import (
    _get_type_2_configs_for_carrier,
    _heal_balance,
    recompute_on_load,
)


class _FakeDoc:
    """Minimal stand-in for a Frappe Document used in unit tests."""

    def __init__(self, doctype, name, **fields):
        self.doctype = doctype
        self.name = name
        self._fields = fields

    def get(self, fieldname, default=None):
        return self._fields.get(fieldname, default)

    def set(self, fieldname, value):
        self._fields[fieldname] = value


class TestRecomputeOnLoadFastExits(unittest.TestCase):
    """Verify that recompute_on_load exits immediately in bypass conditions."""

    def test_skips_when_engine_flag_set(self):
        """No DB call should happen when ledgerly_engine_writing is True."""
        frappe.flags.ledgerly_engine_writing = True
        try:
            with patch(
                "ledgerly.core.balance_recompute._get_type_2_configs_for_carrier"
            ) as mock_lookup:
                recompute_on_load(_FakeDoc("SomeDocType", "S-001"))
                mock_lookup.assert_not_called()
        finally:
            frappe.flags.pop("ledgerly_engine_writing", None)

    def test_skips_outside_web_request(self):
        """No healing when frappe.local.request is absent (background job)."""
        original = getattr(frappe.local, "request", _sentinel := object())
        try:
            if hasattr(frappe.local, "request"):
                del frappe.local.request
            with patch(
                "ledgerly.core.balance_recompute._get_type_2_configs_for_carrier"
            ) as mock_lookup:
                recompute_on_load(_FakeDoc("SomeDocType", "S-001"))
                mock_lookup.assert_not_called()
        finally:
            if original is not _sentinel:
                frappe.local.request = original

    def test_skips_when_no_type_2_config_for_carrier(self):
        """No healing attempt when the doctype is not a carrier."""
        with patch("frappe.local") as mock_local:
            mock_local.request = object()  # simulate web request
            with patch(
                "ledgerly.core.balance_recompute._get_type_2_configs_for_carrier",
                return_value=[],
            ):
                with patch("ledgerly.core.balance_recompute._heal_balance") as mock_heal:
                    recompute_on_load(_FakeDoc("NotACarrier", "X-001"))
                    mock_heal.assert_not_called()


class TestHealBalance(unittest.TestCase):
    """Unit tests for _heal_balance — mocked at the frappe layer."""

    def _make_config(self, sources=None):
        """Return a minimal mock Ledger Config object."""
        cfg = frappe._dict(
            name="LC-001",
            balance_field="balance",
            sources=sources or [],
        )
        return cfg

    def test_no_entries_means_no_write(self):
        """If no Ledger Entries exist for this carrier, balance field is untouched."""
        doc = _FakeDoc("Customer", "CUST-001", balance=5000.0)

        with patch("frappe.get_cached_doc") as mock_get:
            source_row = frappe._dict(
                is_active=1,
                source_doctype="Invoice",
                carrier_link_field="customer",
            )
            mock_get.return_value = self._make_config(sources=[source_row])

            with patch("frappe.get_all") as mock_all, patch("frappe.db.set_value") as mock_set:
                # source docs: none link to this carrier
                mock_all.side_effect = [
                    [],  # source_names query
                ]
                _heal_balance(doc, "LC-001", "balance")
                mock_set.assert_not_called()

    def test_no_drift_means_no_write(self):
        """If computed balance matches current value, no DB write."""
        doc = _FakeDoc("Customer", "CUST-001", balance=100.0)

        with patch("frappe.get_cached_doc") as mock_get:
            source_row = frappe._dict(
                is_active=1,
                source_doctype="Invoice",
                carrier_link_field="customer",
            )
            mock_get.return_value = self._make_config(sources=[source_row])

            with patch("frappe.get_all") as mock_all, patch("frappe.db.set_value") as mock_set:
                mock_all.side_effect = [
                    ["INV-001", "INV-002"],       # source names
                    [{"delta": 60.0}, {"delta": 40.0}],  # entries
                ]
                _heal_balance(doc, "LC-001", "balance")
                mock_set.assert_not_called()

    def test_drift_triggers_silent_write(self):
        """Drifted balance is corrected via set_value without bumping modified."""
        doc = _FakeDoc("Customer", "CUST-001", balance=999.0)

        with patch("frappe.get_cached_doc") as mock_get:
            source_row = frappe._dict(
                is_active=1,
                source_doctype="Invoice",
                carrier_link_field="customer",
            )
            mock_get.return_value = self._make_config(sources=[source_row])

            with patch("frappe.get_all") as mock_all, patch("frappe.db.set_value") as mock_set:
                mock_all.side_effect = [
                    ["INV-001"],              # source names
                    [{"delta": 250.0}],       # entries — correct total is 250
                ]
                _heal_balance(doc, "LC-001", "balance")
                mock_set.assert_called_once_with(
                    "Customer", "CUST-001", "balance", 250.0, update_modified=False
                )
                self.assertAlmostEqual(doc.get("balance"), 250.0)

    def test_inactive_sources_are_skipped(self):
        """Sources with is_active=0 do not contribute to the recompute."""
        doc = _FakeDoc("Customer", "CUST-001", balance=0.0)

        with patch("frappe.get_cached_doc") as mock_get:
            inactive_row = frappe._dict(
                is_active=0,
                source_doctype="Invoice",
                carrier_link_field="customer",
            )
            mock_get.return_value = self._make_config(sources=[inactive_row])

            with patch("frappe.get_all") as mock_all, patch("frappe.db.set_value") as mock_set:
                _heal_balance(doc, "LC-001", "balance")
                mock_all.assert_not_called()
                mock_set.assert_not_called()


@unittest.skipUnless(
    frappe.conf.get("developer_mode"),
    "DB-level tests require developer_mode=1.",
)
class TestGetType2ConfigsForCarrier(unittest.TestCase):
    """Verify _get_type_2_configs_for_carrier queries the DB correctly."""

    def test_returns_empty_for_unknown_doctype(self):
        result = _get_type_2_configs_for_carrier("NonExistentDocType XYZ")
        self.assertEqual(result, [])
