# Copyright (c) 2026, Ledgerly Contributors
# License: TBD. See license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import get_datetime

# Numeric fieldtypes valid as a "tracked field".
NUMERIC_FIELDTYPES = ("Currency", "Int", "Float")

# Fieldtypes valid as a "posting date field".
DATE_FIELDTYPES = ("Date", "Datetime")

# Fieldtypes valid as a "posting time field".
TIME_FIELDTYPES = ("Time",)

# Fieldtypes valid as a "narration field".
TEXT_FIELDTYPES = ("Data", "Small Text", "Text", "Long Text")

# Posting date source options. Mirrors the Select in ledger_config.json.
POSTING_SOURCE_MODIFIED = "Document modification time"
POSTING_SOURCE_FIELD = "Field on source DocType"

# Value source mode options.
VALUE_MODE_FIELD = "Field on document"
VALUE_MODE_CHILD = "Sum across child rows"

# Default cap on number of dimensions per Ledger Config.
DEFAULT_MAX_DIMENSIONS = 5


class LedgerConfig(Document):
    """Configuration for a custom ledger.

    Defines a source DocType, the numeric field to track, how the posting
    datetime should be determined, and Link fields on the source DocType
    to use as reporting dimensions. The engine (PR #5) reads these configs
    to know how to react to source-document changes.
    """

    def validate(self):
        self._validate_source_doctype()
        self._validate_value_source_mode()
        self._validate_child_table_field()
        self._validate_tracked_field()
        self._validate_narration_field()
        self._validate_posting_date_source()
        self._validate_posting_date_field()
        self._validate_posting_time_field()
        self._validate_dimensions()
        self._enrich_dimensions()

    def on_update(self):
        old = self.get_doc_before_save()
        old_source = old.source_doctype if old else None
        new_source = self.source_doctype

        # If source doctype changed, the old doctype's script may no longer be
        # needed — this config is no longer targeting it.
        if old_source and old_source != new_source:
            _sync_client_script(old_source)

        _sync_client_script(new_source)

    def on_trash(self):
        # The record still exists in the DB when on_trash fires, so pass
        # exclude_self=True so the "any active configs remaining?" check
        # doesn't count the record being deleted.
        _sync_client_script(self.source_doctype, exclude_config=self.name)

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

    def _validate_value_source_mode(self):
        """value_source_mode must be one of the allowed values."""
        if self.value_source_mode not in (VALUE_MODE_FIELD, VALUE_MODE_CHILD):
            frappe.throw(
                _("Track Value From must be '{0}' or '{1}'.").format(
                    VALUE_MODE_FIELD, VALUE_MODE_CHILD
                )
            )

        # Clear stale child_table_field if user switches back to "field on document".
        if self.value_source_mode == VALUE_MODE_FIELD:
            self.child_table_field = None

    def _validate_child_table_field(self):
        """If child mode, child_table_field must exist on source and be a Table."""
        if self.value_source_mode != VALUE_MODE_CHILD:
            return

        if not self.child_table_field:
            frappe.throw(_("Child Table Field is required when 'Track Value From' is set to '{0}'.")
                         .format(VALUE_MODE_CHILD))

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
        """Tracked field must be numeric and live on parent or child meta."""
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

    def _validate_narration_field(self):
        """Narration field, if set, must be a text field on the source DocType."""
        if not self.narration_field:
            return
        meta = frappe.get_meta(self.source_doctype)
        df = meta.get_field(self.narration_field)
        if not df:
            frappe.throw(
                _("Narration Field '{0}' does not exist on {1}.").format(
                    self.narration_field, self.source_doctype
                )
            )
        if df.fieldtype not in TEXT_FIELDTYPES:
            frappe.throw(
                _("Narration Field '{0}' on {1} must be a text field (got {2}).").format(
                    self.narration_field, self.source_doctype, df.fieldtype
                )
            )

    def _validate_posting_date_source(self):
        """posting_date_source is required and must be one of the allowed values."""
        if not self.posting_date_source:
            frappe.throw(
                _("Posting Date Source is required. Pick '{0}' for masters or '{1}' for "
                  "transactional / measurement-dated docs.").format(
                    POSTING_SOURCE_MODIFIED, POSTING_SOURCE_FIELD
                )
            )
        if self.posting_date_source not in (POSTING_SOURCE_MODIFIED, POSTING_SOURCE_FIELD):
            frappe.throw(
                _("Posting Date Source must be '{0}' or '{1}'.").format(
                    POSTING_SOURCE_MODIFIED, POSTING_SOURCE_FIELD
                )
            )

        # Clear stale field selections if user switches back to modification time.
        if self.posting_date_source == POSTING_SOURCE_MODIFIED:
            self.posting_date_field = None
            self.posting_time_field = None

    def _validate_posting_date_field(self):
        """If posting source is a field, validate it exists and is Date / Datetime."""
        if self.posting_date_source != POSTING_SOURCE_FIELD:
            return

        if not self.posting_date_field:
            frappe.throw(
                _("Posting Date Field is required when Posting Date Source is '{0}'.").format(
                    POSTING_SOURCE_FIELD
                )
            )

        meta = frappe.get_meta(self.source_doctype)
        df = meta.get_field(self.posting_date_field)
        if not df:
            frappe.throw(
                _("Posting Date Field '{0}' does not exist on {1}.").format(
                    self.posting_date_field, self.source_doctype
                )
            )
        if df.fieldtype not in DATE_FIELDTYPES:
            frappe.throw(
                _("Posting Date Field '{0}' on {1} must be Date or Datetime (got {2}).").format(
                    self.posting_date_field, self.source_doctype, df.fieldtype
                )
            )

    def _validate_posting_time_field(self):
        """If a time field is set, it must be a Time field; only meaningful with a Date."""
        if not self.posting_time_field:
            return

        # Time field only meaningful in field-source mode.
        if self.posting_date_source != POSTING_SOURCE_FIELD:
            frappe.throw(
                _("Posting Time Field can only be set when Posting Date Source is '{0}'.").format(
                    POSTING_SOURCE_FIELD
                )
            )

        meta = frappe.get_meta(self.source_doctype)
        df = meta.get_field(self.posting_time_field)
        if not df:
            frappe.throw(
                _("Posting Time Field '{0}' does not exist on {1}.").format(
                    self.posting_time_field, self.source_doctype
                )
            )
        if df.fieldtype not in TIME_FIELDTYPES:
            frappe.throw(
                _("Posting Time Field '{0}' on {1} must be a Time field (got {2}).").format(
                    self.posting_time_field, self.source_doctype, df.fieldtype
                )
            )

        # If the date field is already Datetime, a separate time field is redundant.
        date_df = meta.get_field(self.posting_date_field)
        if date_df and date_df.fieldtype == "Datetime":
            frappe.throw(
                _("Posting Time Field is redundant when Posting Date Field '{0}' is a Datetime. "
                  "Clear the time field or change the date field to a Date.").format(
                    self.posting_date_field
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
    # Runtime helpers — used by the engine in PR #5
    # ------------------------------------------------------------------

    def _tracked_field_doctype(self):
        """Return the DocType that owns the tracked field (parent or child)."""
        if self.value_source_mode != VALUE_MODE_CHILD or not self.child_table_field:
            return self.source_doctype

        parent_meta = frappe.get_meta(self.source_doctype)
        child_df = parent_meta.get_field(self.child_table_field)
        return child_df.options

    def resolve_posting_datetime(self, source_doc):
        """Determine the effective posting datetime for a ledger entry.

        Called by the engine (PR #5) when a source document change triggers a
        ledger entry. Reads the configured source (modification time, or a
        field on the source doc) and returns a Python datetime.

        Args:
            source_doc: The Document instance being saved (an instance of
                ``self.source_doctype``).

        Returns:
            datetime: The effective posting datetime.
        """
        if self.posting_date_source == POSTING_SOURCE_MODIFIED:
            # `modified` is set by Frappe immediately before saving. On first
            # insert it equals `creation`. Either way, this is the moment of
            # the change.
            return get_datetime(source_doc.modified or frappe.utils.now())

        # Field-source mode.
        date_value = source_doc.get(self.posting_date_field)
        if not date_value:
            frappe.throw(
                _("Cannot create ledger entry: source field '{0}' is empty on {1} {2}.").format(
                    self.posting_date_field, source_doc.doctype, source_doc.name
                )
            )

        date_dt = get_datetime(date_value)

        # Contract: posting_datetime is NEVER returned with a null time component.
        # get_datetime() on a pure date yields 00:00:00, which is what we want
        # as the safe default. If a separate posting_time_field is configured
        # AND has a value, we overlay it. If the time field exists but is empty
        # on this particular source doc, we keep 00:00:00 rather than failing —
        # an empty time is a reasonable user signal for "midnight" semantics.
        if self.posting_time_field:
            time_value = source_doc.get(self.posting_time_field)
            if time_value:
                # frappe.utils.get_time returns a datetime.time on most paths.
                time_part = frappe.utils.get_time(time_value)
                date_dt = date_dt.replace(
                    hour=time_part.hour,
                    minute=time_part.minute,
                    second=time_part.second,
                    microsecond=0,
                )

        # Defensive: zero out microseconds for stable equality comparisons.
        return date_dt.replace(microsecond=0)


# ------------------------------------------------------------------
# Whitelisted helpers for the client script
# ------------------------------------------------------------------


def _disambiguate(items: list[dict]) -> list[dict]:
    """Append ' (fieldname)' to the label of any item whose label is not unique in the list."""
    counts: dict[str, int] = {}
    for item in items:
        counts[item["label"]] = counts.get(item["label"], 0) + 1
    return [
        {
            "value": item["value"],
            "label": (
                f"{item['label']} ({item['value']})" if counts[item["label"]] > 1 else item["label"]
            ),
        }
        for item in items
    ]


@frappe.whitelist()
def get_field_options(source_doctype: str, child_table_field: str | None = None) -> dict:
    """Return field-name options for the Ledger Config form's selects.

    Called by the client script when the user picks a source DocType (and
    optionally a child table). Returns lists used to populate the
    ``tracked_field``, ``child_table_field``, ``posting_date_field``,
    ``posting_time_field``, and dimension fieldname selects.

    Args:
        source_doctype: The DocType selected by the user.
        child_table_field: If set, return tracked-field candidates from this
            child table instead of the parent.

    Returns:
        Dict with keys ``tracked_fields``, ``child_table_fields``,
        ``dimension_fields``, ``posting_date_fields``, ``posting_time_fields``,
        ``narration_fields``.  Each value is a list of ``{value, label}`` dicts
        where ``value`` is the fieldname and ``label`` is the human-readable
        display text (with ``(fieldname)`` suffix when labels collide).
    """
    # Permission check: caller must be able to read the source DocType's meta.
    if not frappe.has_permission("DocType", "read", source_doctype):
        frappe.throw(_("Insufficient permissions to read DocType '{0}'.").format(source_doctype))

    empty = {
        "tracked_fields": [],
        "child_table_fields": [],
        "dimension_fields": [],
        "posting_date_fields": [],
        "posting_time_fields": [],
        "narration_fields": [],
    }
    if not frappe.db.exists("DocType", source_doctype):
        return empty

    parent_meta = frappe.get_meta(source_doctype)

    # tracked_fields: from child-table meta if specified, else from parent.
    if child_table_field:
        child_df = parent_meta.get_field(child_table_field)
        if child_df and child_df.fieldtype == "Table":
            tracked_source_meta = frappe.get_meta(child_df.options)
        else:
            tracked_source_meta = parent_meta
    else:
        tracked_source_meta = parent_meta

    tracked_fields = _disambiguate([
        {"value": df.fieldname, "label": df.label or df.fieldname}
        for df in tracked_source_meta.fields
        if df.fieldtype in NUMERIC_FIELDTYPES
    ])

    child_table_fields = _disambiguate([
        {"value": df.fieldname, "label": f"{df.label or df.fieldname} \u2192 {df.options}"}
        for df in parent_meta.fields
        if df.fieldtype == "Table"
    ])

    dimension_fields = _disambiguate([
        {"value": df.fieldname, "label": f"{df.label or df.fieldname} \u2192 {df.options}"}
        for df in parent_meta.fields
        if df.fieldtype == "Link"
    ])

    # When child_table_field is set, also surface date/time/text fields from
    # the child doctype so users can use e.g. a line-item date as posting date.
    # Child fields are prefixed with "[Child] " to distinguish them visually.
    child_meta = None
    if child_table_field:
        child_df_meta = parent_meta.get_field(child_table_field)
        if child_df_meta and child_df_meta.fieldtype == "Table":
            child_meta = frappe.get_meta(child_df_meta.options)

    def _fields_from(meta, fieldtypes, prefix=""):
        return [
            {"value": df.fieldname, "label": f"{prefix}{df.label or df.fieldname}"}
            for df in meta.fields
            if df.fieldtype in fieldtypes
        ]

    posting_date_fields = _fields_from(parent_meta, DATE_FIELDTYPES)
    posting_time_fields = _fields_from(parent_meta, TIME_FIELDTYPES)
    narration_fields = _fields_from(parent_meta, TEXT_FIELDTYPES)

    if child_meta:
        posting_date_fields += _fields_from(child_meta, DATE_FIELDTYPES, prefix="[Child] ")
        posting_time_fields += _fields_from(child_meta, TIME_FIELDTYPES, prefix="[Child] ")
        narration_fields += _fields_from(child_meta, TEXT_FIELDTYPES, prefix="[Child] ")

    return {
        "tracked_fields": tracked_fields,
        "child_table_fields": child_table_fields,
        "dimension_fields": dimension_fields,
        "posting_date_fields": _disambiguate(posting_date_fields),
        "posting_time_fields": _disambiguate(posting_time_fields),
        "narration_fields": _disambiguate(narration_fields),
    }


@frappe.whitelist()
def get_config_meta(name: str) -> dict:
    """Return config metadata used by the Custom Ledger report's dynamic filters.

    Called by the report's JS when the Ledger Config filter changes so the
    report can update Source Document and dimension filter labels/options.
    """
    if not frappe.has_permission("Ledger Config", "read", name):
        frappe.throw(_("Insufficient permissions to read Ledger Config '{0}'.").format(name))

    config = frappe.get_cached_doc("Ledger Config", name)
    return {
        "ledger_name": config.ledger_name,
        "source_doctype": config.source_doctype,
        "narration_field": config.narration_field,
        "dimensions": [
            {
                "fieldname": f"dim_{idx}",
                "label": dim.label or dim.link_doctype,
                "link_doctype": dim.link_doctype,
            }
            for idx, dim in enumerate(config.dimensions or [], start=1)
            if idx <= 5
        ],
    }


@frappe.whitelist()
def get_field_type(source_doctype: str, fieldname: str) -> str | None:
    """Return the fieldtype of a single field on the given DocType.

    Used by the Ledger Config client script to decide whether to hide the
    ``posting_time_field`` (which is redundant if the picked date field is
    a Datetime).

    Args:
        source_doctype: DocType to inspect.
        fieldname: Field on that DocType.

    Returns:
        The fieldtype string (e.g. ``"Date"``, ``"Datetime"``), or ``None``
        if the field or DocType doesn't exist.
    """
    if not frappe.has_permission("DocType", "read", source_doctype):
        frappe.throw(_("Insufficient permissions to read DocType '{0}'.").format(source_doctype))

    if not frappe.db.exists("DocType", source_doctype):
        return None

    meta = frappe.get_meta(source_doctype)
    df = meta.get_field(fieldname)
    return df.fieldtype if df else None


# ------------------------------------------------------------------
# Client Script lifecycle helpers
# ------------------------------------------------------------------

_CLIENT_SCRIPT_PREFIX = "Ledgerly - "


def _cs_name(source_doctype: str) -> str:
    return f"{_CLIENT_SCRIPT_PREFIX}{source_doctype}"


def _sync_client_script(source_doctype: str, exclude_config: str | None = None) -> None:
    """Create or delete the auto-generated Client Script for source_doctype.

    Checks whether any active Ledger Config (other than exclude_config, used
    when a config is being deleted) still targets source_doctype. Creates
    the script when at least one remains, deletes it when none do.
    """
    if not source_doctype:
        return

    filters: dict = {"source_doctype": source_doctype, "is_active": 1}
    if exclude_config:
        filters["name"] = ["!=", exclude_config]

    if frappe.db.exists("Ledger Config", filters):
        _upsert_client_script(source_doctype)
    else:
        _delete_client_script(source_doctype)


def _upsert_client_script(source_doctype: str) -> None:
    """Create the Client Script if absent; update the script body if present."""
    name = _cs_name(source_doctype)
    content = _build_client_script(source_doctype)

    if frappe.db.exists("Client Script", name):
        doc = frappe.get_doc("Client Script", name)
        doc.script = content
        doc.enabled = 1
        doc.save(ignore_permissions=True)
    else:
        doc = frappe.get_doc(
            {
                "doctype": "Client Script",
                "name": name,
                "dt": source_doctype,
                "script": content,
                "enabled": 1,
            }
        )
        doc.insert(ignore_permissions=True)


def _delete_client_script(source_doctype: str) -> None:
    """Remove the auto-generated Client Script for source_doctype, if present."""
    name = _cs_name(source_doctype)
    if frappe.db.exists("Client Script", name):
        frappe.delete_doc("Client Script", name, ignore_permissions=True, force=True)


def _build_client_script(source_doctype: str) -> str:
    """Return the JS body for the auto-generated Client Script.

    Wrapped in an IIFE so nothing leaks into the global scope. The
    deduplication guard (frm._ledgerly_viewed) prevents duplicate API
    calls when multiple Client Scripts happen to load for the same form,
    and is cleared on each refresh so buttons stay live after saves.
    """
    import json  # local import — only used during config save, not at import time

    dt = json.dumps(source_doctype)
    method = json.dumps(
        "ledgerly.ledgerly.api.source_doctype_buttons.get_ledger_views_for_record"
    )
    report_url = "/app/query-report/Custom%20Ledger"

    return (
        "(function () {\n"
        f"    frappe.ui.form.on({dt}, {{\n"
        "        refresh: function (frm) {\n"
        "            if (frm.is_new()) return;\n"
        "\n"
        "            frappe.call({\n"
        f"                method: {method},\n"
        "                args: { doctype: frm.doctype, name: frm.docname },\n"
        "                callback: function (r) {\n"
        "                    var configs = r.message || [];\n"
        "                    if (!configs.length) return;\n"
        "\n"
        "                    if (configs.length === 1) {\n"
        "                        frm.add_custom_button(__('View Ledger'), function () {\n"
        "                            _lgl_open(configs[0].config_name, frm.docname);\n"
        "                        });\n"
        "                    } else {\n"
        "                        configs.forEach(function (cfg) {\n"
        "                            frm.add_custom_button(cfg.config_label, function () {\n"
        "                                _lgl_open(cfg.config_name, frm.docname);\n"
        "                            }, __('Ledger'));\n"
        "                        });\n"
        "                    }\n"
        "                }\n"
        "            });\n"
        "        }\n"
        "    });\n"
        "\n"
        "    function _lgl_open(cfg, rec) {\n"
        f"        var url = '{report_url}?ledger_config=' +\n"
        "            encodeURIComponent(cfg) + '&source_name=' + encodeURIComponent(rec);\n"
        "        window.open(url, '_blank');\n"
        "    }\n"
        "})();\n"
    )
