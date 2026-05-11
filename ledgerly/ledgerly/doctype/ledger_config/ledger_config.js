// Copyright (c) 2026, Ledgerly Contributors
// License: TBD. See license.txt

frappe.ui.form.on("Ledger Config", {
    refresh: function (frm) {
        if (frm.doc.source_doctype) {
            ledgerly.fetch_field_options(frm);
        }
    },

    source_doctype: function (frm) {
        // Clear all dependent fields when source changes.
        frm.set_value("tracked_field", null);
        frm.set_value("child_table_field", null);
        frm.set_value("posting_date_field", null);
        frm.set_value("posting_time_field", null);
        frm.clear_table("dimensions");
        frm.refresh_field("dimensions");

        if (frm.doc.source_doctype) {
            ledgerly.fetch_field_options(frm);
        }
    },

    value_source_mode: function (frm) {
        // Switching modes invalidates the current tracked_field choice.
        frm.set_value("tracked_field", null);
        if (frm.doc.value_source_mode === "Field on document") {
            frm.set_value("child_table_field", null);
        }
        if (frm.doc.source_doctype) {
            ledgerly.fetch_field_options(frm);
        }
    },

    child_table_field: function (frm) {
        // Tracked field candidates depend on the child table choice.
        frm.set_value("tracked_field", null);
        if (frm.doc.source_doctype) {
            ledgerly.fetch_field_options(frm);
        }
    },

    posting_date_source: function (frm) {
        // Clear field selections if user switches back to modification time.
        if (frm.doc.posting_date_source === "Document modification time") {
            frm.set_value("posting_date_field", null);
            frm.set_value("posting_time_field", null);
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
            child_table_field:
                frm.doc.value_source_mode === "Sum across child rows"
                    ? frm.doc.child_table_field || null
                    : null,
        },
        callback: function (r) {
            if (!r.message) {
                return;
            }

            const set_select = (fieldname, values) => {
                const options = ["", ...values.map((f) => f.value)];
                frm.set_df_property(fieldname, "options", options.join("\n"));
                frm.refresh_field(fieldname);
            };

            set_select("tracked_field", r.message.tracked_fields);
            set_select("child_table_field", r.message.child_table_fields);
            set_select("posting_date_field", r.message.posting_date_fields);
            set_select("posting_time_field", r.message.posting_time_fields);

            // Dimensions grid: dimension_fieldname is a Data field in the
            // child schema, but we treat it as a Select at the UI level
            // by overriding the docfield property in the grid.
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
            frm.refresh_field("dimensions");
        },
    });
};
