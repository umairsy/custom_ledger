# Copyright (c) 2026, Custom Ledger Contributors
# License: TBD. See license.txt

import frappe
from frappe.model.document import Document


class LedgerDimension(Document):
    """Child row on Ledger Config — declares one dimension field from the source DocType.

    Validation that the fieldname actually exists on the source DocType and is a Link
    field happens in the Ledger Config parent controller, since that's where we have
    access to ``parent.source_doctype``. This controller stays intentionally minimal.
    """

    def validate(self):
        if self.dimension_fieldname:
            self.dimension_fieldname = self.dimension_fieldname.strip()
            if " " in self.dimension_fieldname:
                frappe.throw(
                    frappe._("Dimension Fieldname must not contain spaces. Got: {0}").format(
                        self.dimension_fieldname
                    )
                )
