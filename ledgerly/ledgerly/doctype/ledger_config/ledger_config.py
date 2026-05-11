# Copyright (c) 2026, Ledgerly Contributors
# License: TBD. See license.txt

import frappe
from frappe import _
from frappe.model.document import Document

# Numeric fieldtypes that are valid as a "tracked field".
NUMERIC_FIELDTYPES = ("Currency", "Int", "Float")

# Default cap on number of dimensions per Ledger Config.
# Overridable via site config: `ledgerly_max_dimensions`.
DEFAULT_MAX_DIMENSIONS = 5


class LedgerConfig(Document):
    """Configuration for a custom ledger.

    Defines a source DocType, the numeric field whose changes to log, and the
    Link fields on that DocType to use as reporting dimensions. The actual
    ledger-entry creation engine (PR #5) reads these configs to know what to do.
    """

    def validate(self):
        self._validate_source_doctype()
        self._validate_child_table_field()
        self._validate_tracked_field()
        self._validate_dimensions()
        self._enrich_dimensions()

    # ------------------------------------------------------------------
    # Validation helpers
    # ------------------------------------------------------------------

    def _validate_source_doctype(self):
        """Source must exist and be a real, non-child DocType."""
        if not frappe.db.exists("DocType", self.source_doctype):
            frappe.throw(_("Source DocType '{0}' does not exist.").format(self.source_doctype))

        meta = frappe.get_meta(self.source_doctype)
        if meta.istable:
            frappe.throw(
                _("Source DocType cannot be a child table. Got: {0}").format(self.source_doctype)
            )

    def _validate_child_table_field(self):
        """If child_table_field is set, it must exist on source and be a Table field."""
        if not self.child_table_field:
            return

        meta = frappe.get_meta(self.source_doctype)
        df = meta.get_field(self.child_table_field)
        if not df:
            frappe.throw(
                _("Child table field '{0}' does not exist on {1}.").format(
                    self.child_table_field, self.source_doctype
                )
            )
        if df.fieldtype != "Table":
            frappe.throw(
                _("Field '{0}' on {1} is not a Table field (it is {2}).").format(
                    self.child_table_field, self.source_doctype, df.fieldtype
                )
            )

    def _validate_tracked_field(self):
        """Tracked field must be numeric and live on the right meta (parent or child)."""
        target_doctype = self._tracked_field_doctype()
        meta = frappe.get_meta(target_doctype)
        df = meta.get_field(self.tracked_field)
        if not df:
            frappe.throw(
                _("Tracked field '{0}' does not exist on {1}.").format(
                    self.tracked_field, target_doctype
                )
            )
        if df.fieldtype not in NUMERIC_FIELDTYPES:
            frappe.throw(
                _("Tracked field '{0}' on {1} must be one of {2} (got {3}).").format(
                    self.tracked_field,
                    target_doctype,
                    ", ".join(NUMERIC_FIELDTYPES),
                    df.fieldtype,
                )
            )

    def _validate_dimensions(self):
        """Each dimension must be a Link field on the source DocType. No duplicates."""
        max_dims = frappe.local.conf.get("ledgerly_max_dimensions", DEFAULT_MAX_DIMENSIONS)
        if len(self.dimensions or []) > max_dims:
            frappe.throw(
                _("Too many dimensions. Maximum allowed is {0}; got {1}.").format(
                    max_dims, len(self.dimensions)
                )
            )

        seen = set()
        parent_meta = frappe.get_meta(self.source_doctype)
        for row in self.dimensions or []:
            fieldname = (row.dimension_fieldname or "").strip()
            if not fieldname:
                frappe.throw(_("Dimension Fieldname is required for every dimension row."))

            if fieldname in seen:
                frappe.throw(_("Duplicate dimension: '{0}'.").format(fieldname))
            seen.add(fieldname)

            df = parent_meta.get_field(fieldname)
            if not df:
                frappe.throw(
                    _("Dimension field '{0}' does not exist on {1}.").format(
                        fieldname, self.source_doctype
                    )
                )
            if df.fieldtype != "Link":
                frappe.throw(
                    _("Dimension field '{0}' on {1} must be a Link field (got {2}).").format(
                        fieldname, self.source_doctype, df.fieldtype
                    )
                )

    def _enrich_dimensions(self):
        """Auto-populate label and link_doctype on each dimension row from source meta."""
        if not self.dimensions:
            return

        parent_meta = frappe.get_meta(self.source_doctype)
        for row in self.dimensions:
            df = parent_meta.get_field(row.dimension_fieldname)
            row.label = df.label or df.fieldname
            row.link_doctype = df.options

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _tracked_field_doctype(self):
        """Return the DocType that owns the tracked field (parent or child)."""
        if not self.child_table_field:
            return self.source_doctype

        parent_meta = frappe.get_meta(self.source_doctype)
        child_df = parent_meta.get_field(self.child_table_field)
        # Validated earlier; if we got here, child_df is a Table field with options.
        return child_df.options


# ------------------------------------------------------------------
# Whitelisted helpers for the client script
# ------------------------------------------------------------------


@frappe.whitelist()
def get_field_options(source_doctype: str, child_table_field: str | None = None) -> dict:
    """Return field-name options for the Ledger Config form's selects.

    Called by the client script when the user picks a source DocType (and
    optionally a child table). Returns three lists used to populate the
    `tracked_field`, `child_table_field`, and dimension fieldname selects.

    Args:
        source_doctype: The DocType selected by the user.
        child_table_field: If set, return tracked-field candidates from this
            child table instead of the parent.

    Returns:
        Dict with keys ``tracked_fields``, ``child_table_fields``,
        ``dimension_fields``. Each value is a list of ``{value, label}`` dicts.
    """
    # Permission check: the caller must be able to read the source DocType's meta.
    if not frappe.has_permission("DocType", "read", source_doctype):
        frappe.throw(_("Insufficient permissions to read DocType '{0}'.").format(source_doctype))

    if not frappe.db.exists("DocType", source_doctype):
        return {"tracked_fields": [], "child_table_fields": [], "dimension_fields": []}

    parent_meta = frappe.get_meta(source_doctype)

    # tracked_fields: from child-table meta if specified, else from parent.
    if child_table_field:
        child_df = parent_meta.get_field(child_table_field)
        if child_df and child_df.fieldtype == "Table":
            child_meta = frappe.get_meta(child_df.options)
            tracked_source_meta = child_meta
        else:
            tracked_source_meta = parent_meta
    else:
        tracked_source_meta = parent_meta

    tracked_fields = [
        {"value": df.fieldname, "label": f"{df.label or df.fieldname} ({df.fieldtype})"}
        for df in tracked_source_meta.fields
        if df.fieldtype in NUMERIC_FIELDTYPES
    ]

    child_table_fields = [
        {"value": df.fieldname, "label": f"{df.label or df.fieldname} → {df.options}"}
        for df in parent_meta.fields
        if df.fieldtype == "Table"
    ]

    # Dimensions are always Link fields on the *parent*.
    dimension_fields = [
        {
            "value": df.fieldname,
            "label": f"{df.label or df.fieldname} → {df.options}",
        }
        for df in parent_meta.fields
        if df.fieldtype == "Link"
    ]

    return {
        "tracked_fields": tracked_fields,
        "child_table_fields": child_table_fields,
        "dimension_fields": dimension_fields,
    }
