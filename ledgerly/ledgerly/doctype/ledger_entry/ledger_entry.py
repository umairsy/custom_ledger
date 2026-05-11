# Copyright (c) 2026, Ledgerly Contributors
# License: TBD. See license.txt

import hashlib

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import get_datetime, get_time


class LedgerEntry(Document):
    """One row in a custom ledger.

    Created programmatically by the engine (PR #5) when a tracked field changes
    on a source document. Submittable for audit immutability. Cancellation
    creates a new ledger event but does not delete history (docstatus=2).
    """

    def validate(self):
        self._compose_posting_datetime()
        self._compute_change_signature()

    def before_submit(self):
        self._compose_posting_datetime()
        self._compute_change_signature()

    def on_trash(self):
        """Prevent hard deletion of submitted entries."""
        if self.docstatus == 1:
            frappe.throw(
                _("Cannot delete a submitted Ledger Entry. Cancel it instead to preserve "
                  "audit history.")
            )

    def _compose_posting_datetime(self):
        """Combine posting_date and posting_time into the canonical datetime."""
        if not self.posting_date:
            frappe.throw(_("Posting Date is required."))
        if not self.posting_time:
            self.posting_time = "00:00:00"

        date_part = get_datetime(self.posting_date)
        time_part = get_time(self.posting_time)
        self.posting_datetime = date_part.replace(
            hour=time_part.hour,
            minute=time_part.minute,
            second=time_part.second,
            microsecond=0,
        )

    def _compute_change_signature(self):
        """Hash of (source_doctype, source_name, posting_datetime, value)."""
        if not (self.source_name and self.posting_datetime and self.value is not None):
            return

        payload = "|".join(
            [
                self.source_doctype or "",
                self.source_name or "",
                self.posting_datetime.isoformat() if hasattr(self.posting_datetime, "isoformat")
                else str(self.posting_datetime),
                f"{float(self.value):.6f}",
            ]
        ).encode("utf-8")
        self.change_signature = hashlib.sha256(payload).hexdigest()[:32]
