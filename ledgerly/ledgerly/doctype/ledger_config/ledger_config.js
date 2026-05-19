// Copyright (c) 2026, Ledgerly Contributors
// License: TBD. See license.txt

frappe.ui.form.on("Ledger Config", {
    refresh: function (frm) {
        if (frm.doc.source_doctype) {
            ledgerly.fetch_field_options(frm);
        }
        // Re-run posting_date_field handler so the time field is hidden when
        // reopening a Ledger Config that uses a Datetime posting field.
        if (frm.doc.posting_date_field) {
            frm.trigger("posting_date_field");
        } else {
            frm.toggle_display("posting_time_field", false);
        }

        // Buttons — only on saved docs.
        if (!frm.is_new()) {
            frm.add_custom_button(__("View Report"), function () {
                frappe.set_route("query-report", "Custom Ledger", {
                    ledger_config: frm.doc.name,
                });
            });
            frm.add_custom_button(__("View Dashboard"), function () {
                window.open(
                    "/app/ledger-dashboard?config=" + encodeURIComponent(frm.doc.name),
                    "_blank"
                );
            });
        }
    },

    ledger_type: function (frm) {
        // Clear Type 1 fields when switching to Type 2 and vice versa.
        if (frm.doc.ledger_type === "Track balance from transactions") {
            frm.set_value("source_doctype", null);
            frm.set_value("tracked_field", null);
            frm.set_value("child_table_field", null);
            frm.set_value("narration_field", null);
            frm.set_value("posting_date_source", null);
            frm.set_value("posting_date_field", null);
            frm.set_value("posting_time_field", null);
        } else {
            frm.set_value("balance_carrier_doctype", null);
            frm.set_value("balance_field", null);
            frm.clear_table("sources");
            frm.refresh_field("sources");
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
            frm.toggle_display("posting_time_field", false);
        }
    },

    balance_carrier_doctype: function (frm) {
        frm.set_value("balance_field", null);
        if (frm.doc.balance_carrier_doctype) {
            ledgerly.fetch_carrier_fields(frm);
        }
    },

    posting_date_field: function (frm) {
        // When the picked date field is a Datetime, the separate posting_time_field
        // is redundant. Hide it AND clear any value so it can't be saved by mistake.
        if (!frm.doc.posting_date_field || !frm.doc.source_doctype) {
            frm.toggle_display("posting_time_field", false);
            return;
        }

        frappe.call({
            method: "ledgerly.ledgerly.doctype.ledger_config.ledger_config.get_field_type",
            args: {
                source_doctype: frm.doc.source_doctype,
                fieldname: frm.doc.posting_date_field,
            },
            callback: function (r) {
                const fieldtype = r.message;
                if (fieldtype === "Datetime") {
                    // Hide and clear — see PR #4.5 design note.
                    if (frm.doc.posting_time_field) {
                        frm.set_value("posting_time_field", null);
                    }
                    frm.toggle_display("posting_time_field", false);
                } else {
                    // Date — show the time field so the user can optionally pair it.
                    frm.toggle_display("posting_time_field", true);
                }
            },
        });
    },
});

// Namespace ledgerly to avoid polluting the global scope.
window.ledgerly = window.ledgerly || {};

// Ledger Source child table events — fetch field options when source changes.
frappe.ui.form.on("Ledger Source", {
    source_doctype: function (frm, cdt, cdn) {
        var row = locals[cdt][cdn];
        frappe.model.set_value(cdt, cdn, "source_field", null);
        frappe.model.set_value(cdt, cdn, "carrier_link_field", null);
        frappe.model.set_value(cdt, cdn, "posting_date_field", null);
        frappe.model.set_value(cdt, cdn, "posting_time_field", null);
        frappe.model.set_value(cdt, cdn, "child_table_field", null);
        if (row.source_doctype) {
            ledgerly.fetch_source_row_fields(frm, cdt, cdn);
        }
    },
});

ledgerly.fetch_carrier_fields = function (frm) {
    frappe.call({
        method: "ledgerly.ledgerly.doctype.ledger_config.ledger_config.get_field_options",
        args: { source_doctype: frm.doc.balance_carrier_doctype },
        callback: function (r) {
            if (!r.message) return;
            const options_list = r.message.tracked_fields;
            const values = ["", ...options_list.map((f) => f.value)];
            frm.set_df_property("balance_field", "options", values.join("\n"));
            frm.refresh_field("balance_field");

            const field = frm.get_field("balance_field");
            if (field && field.$input) {
                const label_map = {};
                options_list.forEach(function (f) {
                    label_map[f.value] = f.label || f.value;
                });
                field.$input.find("option").each(function () {
                    const val = $(this).val();
                    if (val && label_map[val]) $(this).text(label_map[val]);
                });
            }
        },
    });
};

ledgerly.fetch_source_row_fields = function (frm, cdt, cdn) {
    var row = locals[cdt][cdn];
    frappe.call({
        method: "ledgerly.ledgerly.doctype.ledger_config.ledger_config.get_field_options",
        args: { source_doctype: row.source_doctype },
        callback: function (r) {
            if (!r.message) return;
            var grid = frm.fields_dict.sources && frm.fields_dict.sources.grid;
            if (!grid) return;

            const _set_grid_col = (fieldname, options_list) => {
                const values = ["", ...options_list.map((f) => f.value)];
                grid.update_docfield_property(fieldname, "options", values.join("\n"));
            };

            _set_grid_col("source_field", r.message.tracked_fields);
            _set_grid_col("child_table_field", r.message.child_table_fields);
            _set_grid_col("posting_date_field", r.message.posting_date_fields);
            _set_grid_col("posting_time_field", r.message.posting_time_fields);

            // carrier_link_field: Link fields on source that point to the carrier doctype.
            var carrier = frm.doc.balance_carrier_doctype;
            var link_fields = (r.message.dimension_fields || []).filter(function (f) {
                // dimension_fields includes all Link fields; the user picks the one
                // pointing to balance_carrier_doctype — filter client-side if carrier known.
                return !carrier || f.label.indexOf("→ " + carrier) !== -1;
            });
            // Fall back to all Link fields if none matched.
            if (!link_fields.length) link_fields = r.message.dimension_fields || [];
            _set_grid_col("carrier_link_field", link_fields);

            grid.refresh();
        },
    });
};

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

            const set_select = (fieldname, options_list) => {
                const values = ["", ...options_list.map((f) => f.value)];
                frm.set_df_property(fieldname, "options", values.join("\n"));
                frm.refresh_field(fieldname);

                // Override <option> display text to show human-readable labels
                // while keeping the raw fieldname as the stored value.
                const field = frm.get_field(fieldname);
                if (field && field.$input) {
                    const label_map = {};
                    options_list.forEach(function (f) {
                        label_map[f.value] = f.label || f.value;
                    });
                    field.$input.find("option").each(function () {
                        const val = $(this).val();
                        if (val && label_map[val]) $(this).text(label_map[val]);
                    });
                }
            };

            set_select("tracked_field", r.message.tracked_fields);
            set_select("child_table_field", r.message.child_table_fields);
            set_select("posting_date_field", r.message.posting_date_fields);
            set_select("posting_time_field", r.message.posting_time_fields);
            set_select("narration_field", r.message.narration_fields || []);

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
