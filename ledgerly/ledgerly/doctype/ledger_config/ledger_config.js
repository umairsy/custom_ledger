// Copyright (c) 2026, Ledgerly Contributors
// License: TBD. See license.txt

frappe.ui.form.on("Ledger Config", {
    refresh: function (frm) {
        // Re-populate dropdowns whenever the form loads, in case the source has
        // changed (e.g. custom fields added to the source DocType since last save).
        if (frm.doc.source_doctype) {
            ledgerly.fetch_field_options(frm);
        }
    },

    source_doctype: function (frm) {
        // Clear dependent fields when source changes — they'd be stale otherwise.
        frm.set_value("tracked_field", null);
        frm.set_value("child_table_field", null);
        frm.clear_table("dimensions");
        frm.refresh_field("dimensions");

        if (frm.doc.source_doctype) {
            ledgerly.fetch_field_options(frm);
        }
    },

    child_table_field: function (frm) {
        // Tracked field candidates depend on whether a child table is picked.
        frm.set_value("tracked_field", null);
        if (frm.doc.source_doctype) {
            ledgerly.fetch_field_options(frm);
        }
    },
});

// Namespace ledgerly to avoid polluting the global scope.
window.ledgerly = window.ledgerly || {};

ledgerly.fetch_field_options = function (frm) {
    frappe.call({
        method: "ledgerly.ledgerly.doctype.ledger_config.ledger_config.get_field_options",
        args: {
            source_doctype: frm.doc.source_doctype,
            child_table_field: frm.doc.child_table_field || null,
        },
        callback: function (r) {
            if (!r.message) {
                return;
            }

            // Populate tracked_field select.
            const tracked_options = ["", ...r.message.tracked_fields.map((f) => f.value)];
            frm.set_df_property("tracked_field", "options", tracked_options.join("\n"));

            // Populate child_table_field select.
            const child_options = ["", ...r.message.child_table_fields.map((f) => f.value)];
            frm.set_df_property("child_table_field", "options", child_options.join("\n"));

            // Populate dimension fieldname select inside the grid.
            const dim_options = ["", ...r.message.dimension_fields.map((f) => f.value)];
            const grid = frm.fields_dict.dimensions.grid;
            if (grid) {
                grid.update_docfield_property("dimension_fieldname", "fieldtype", "Select");
                grid.update_docfield_property(
                    "dimension_fieldname",
                    "options",
                    dim_options.join("\n")
                );
                grid.refresh();
            }

            // Refresh visible selects so the new options take effect immediately.
            frm.refresh_field("tracked_field");
            frm.refresh_field("child_table_field");
            frm.refresh_field("dimensions");
        },
    });
};
