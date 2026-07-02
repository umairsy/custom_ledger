// Copyright (c) 2026, Custom Ledger Contributors
// License: TBD. See license.txt

frappe.ui.form.on("Ledger Config", {
    refresh: function (frm) {
        if (frm.doc.source_doctype) {
            custom_ledger.fetch_field_options(frm);
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

            // Maintenance — integrity check + reposting.
            frm.add_custom_button(__("Check Integrity"), function () {
                frappe.call({
                    method: "custom_ledger.core.reposting.check_ledger_integrity",
                    args: { ledger_config: frm.doc.name },
                    freeze: true,
                    freeze_message: __("Scanning ledger…"),
                    callback: function (r) {
                        if (!r.message) return;
                        const count = r.message.anomaly_count;
                        if (!count) {
                            frappe.msgprint({
                                title: __("Ledger is consistent"),
                                message: __("No running-balance anomalies found."),
                                indicator: "green",
                            });
                            return;
                        }
                        const rows = r.message.anomalies
                            .map((a) => "<li>" + frappe.utils.escape_html(JSON.stringify(a)) + "</li>")
                            .join("");
                        frappe.msgprint({
                            title: __("{0} anomalies found", [count]),
                            message: "<ul>" + rows + "</ul>" +
                                (frm.doc.ledger_mutability === "Mutable"
                                    ? __("<p>Use <b>Repost Ledger</b> to fix.</p>")
                                    : __("<p>This ledger is Immutable; anomalies indicate historic data issues.</p>")),
                            indicator: "red",
                        });
                    },
                });
            }, __("Maintenance"));

            frm.add_custom_button(__("Repost Ledger"), function () {
                frappe.confirm(
                    __("Recompute this ledger's running balance? Runs in the background."),
                    function () {
                        frappe.call({
                            method: "custom_ledger.core.reposting.repost_ledger",
                            args: { ledger_config: frm.doc.name },
                            freeze: true,
                            callback: function (r) {
                                frappe.show_alert({
                                    message: __("Repost queued: {0}", [JSON.stringify(r.message)]),
                                    indicator: "blue",
                                });
                            },
                        });
                    }
                );
            }, __("Maintenance"));
        }

        // Type 2 only: re-populate balance_field options on form load so the
        // saved value displays correctly. The balance_carrier_doctype change
        // handler doesn't fire on load.
        if (
            frm.doc.ledger_type === "Track balance from transactions" &&
            frm.doc.balance_carrier_doctype
        ) {
            custom_ledger.fetch_carrier_fields(frm);
        }

        // Pre-populate Ledger Source grid selects for existing rows so stored
        // values display on form load. Two-pass: seed from the stored values
        // immediately (avoids blank-flash in configs with multiple source
        // doctypes), then fire the full fetch per unique source_doctype.
        var _sources_grid = frm.fields_dict.sources && frm.fields_dict.sources.grid;
        if (_sources_grid && frm.doc.sources && frm.doc.sources.length) {
            var _seed = function (fieldname) {
                var vals = frm.doc.sources
                    .map(function (r) { return r[fieldname]; })
                    .filter(Boolean);
                if (vals.length) {
                    _sources_grid.update_docfield_property(
                        fieldname, "options", [""].concat(vals).join("\n")
                    );
                }
            };
            ["source_field", "carrier_link_field",
             "posting_date_field", "posting_time_field"].forEach(_seed);
            _sources_grid.refresh();

            var _seen_dtypes = {};
            frm.doc.sources.forEach(function (row) {
                if (row.source_doctype && !_seen_dtypes[row.source_doctype]) {
                    _seen_dtypes[row.source_doctype] = true;
                    custom_ledger.populate_source_row_selects(frm, "Ledger Source", row.name);
                }
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
            custom_ledger.fetch_field_options(frm);
        }
    },

    value_source_mode: function (frm) {
        // Switching modes invalidates the current tracked_field choice.
        frm.set_value("tracked_field", null);
        if (frm.doc.value_source_mode === "Field on document") {
            frm.set_value("child_table_field", null);
        }
        if (frm.doc.source_doctype) {
            custom_ledger.fetch_field_options(frm);
        }
    },

    child_table_field: function (frm) {
        // Tracked field candidates depend on the child table choice.
        frm.set_value("tracked_field", null);
        if (frm.doc.source_doctype) {
            custom_ledger.fetch_field_options(frm);
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
            custom_ledger.fetch_carrier_fields(frm);
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
            method: "custom_ledger.custom_ledger.doctype.ledger_config.ledger_config.get_field_type",
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

// Namespace custom_ledger to avoid polluting the global scope.
window.custom_ledger = window.custom_ledger || {};

// Ledger Source child table events.
frappe.ui.form.on("Ledger Source", {
    source_doctype: function (frm, cdt, cdn) {
        var row = locals[cdt][cdn];
        frappe.model.set_value(cdt, cdn, "source_field", null);
        frappe.model.set_value(cdt, cdn, "carrier_link_field", null);
        frappe.model.set_value(cdt, cdn, "posting_date_field", null);
        frappe.model.set_value(cdt, cdn, "posting_time_field", null);
        frappe.model.set_value(cdt, cdn, "child_table_field", null);
        if (row.source_doctype) {
            custom_ledger.populate_source_row_selects(frm, cdt, cdn);
        }
    },
    form_render: function (frm, cdt, cdn) {
        // Row editor opened — fetch options for this row's source_doctype so
        // the rendered select widgets show the stored value and a full choice list.
        custom_ledger.populate_source_row_selects(frm, cdt, cdn);
    },
});

custom_ledger.fetch_carrier_fields = function (frm) {
    frappe.call({
        method: "custom_ledger.custom_ledger.doctype.ledger_config.ledger_config.get_field_options",
        args: { source_doctype: frm.doc.balance_carrier_doctype },
        callback: function (r) {
            if (!r.message) return;
            const options_list = r.message.balance_display_fields || [];

            if (options_list.length === 0) {
                frappe.show_alert({
                    message: __(
                        "No suitable field found on {0}. Add a read-only Currency, " +
                        "Float, or Int field on {0} via Customize Form, then re-pick " +
                        "the carrier.",
                        [frm.doc.balance_carrier_doctype]
                    ),
                    indicator: "orange",
                });
            }

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

/**
 * Populate Ledger Source select-field options for one row.
 *
 * Single shared helper used by three render contexts:
 *   • source_doctype change  — user picks a new source doctype
 *   • form_render            — row editor opens for an existing row
 *   • parent refresh         — form loads with existing rows already saved
 *
 * grid.update_docfield_property is grid-wide (not per-row). When rows have
 * different source_doctypes the last resolved call sets the shared grid column
 * options. The parent refresh handler seeds stored values first (no API call)
 * so all rows display correctly while API calls are in flight. The row editor
 * is always correct because form_render fires per-row and the callback also
 * updates grid_form.fields_dict directly for the open editor.
 */
custom_ledger.populate_source_row_selects = function (frm, cdt, cdn) {
    var row = locals[cdt] && locals[cdt][cdn];
    if (!row || !row.source_doctype) return;

    frappe.call({
        method: "custom_ledger.custom_ledger.doctype.ledger_config.ledger_config.get_field_options",
        args: { source_doctype: row.source_doctype },
        callback: function (r) {
            if (!r.message) return;
            var grid = frm.fields_dict.sources && frm.fields_dict.sources.grid;
            if (!grid) return;

            var carrier = frm.doc.balance_carrier_doctype;
            var link_fields = (r.message.dimension_fields || []).filter(function (f) {
                return !carrier || f.label.indexOf("→ " + carrier) !== -1;
            });
            if (!link_fields.length) link_fields = r.message.dimension_fields || [];

            var field_map = {
                source_field:       r.message.tracked_fields || [],
                child_table_field:  r.message.child_table_fields || [],
                posting_date_field: r.message.posting_date_fields || [],
                posting_time_field: r.message.posting_time_fields || [],
                carrier_link_field: link_fields,
            };

            var _opts = function (list) {
                return [""].concat(list.map(function (f) { return f.value; })).join("\n");
            };

            // 1. Update shared grid-column metadata (compact grid + row editor template).
            Object.keys(field_map).forEach(function (fn) {
                grid.update_docfield_property(fn, "options", _opts(field_map[fn]));
            });

            // 2. If this row's editor is open, refresh its rendered fields directly
            //    so the select widgets pick up the new options without re-opening.
            var grid_row = grid.grid_rows_by_name && grid.grid_rows_by_name[cdn];
            if (grid_row && grid_row.grid_form && grid_row.grid_form.fields_dict) {
                Object.keys(field_map).forEach(function (fn) {
                    var field = grid_row.grid_form.fields_dict[fn];
                    if (!field) return;
                    field.df.options = _opts(field_map[fn]);
                    field.refresh();
                });
            }

            // 3. Redraw compact grid rows.
            grid.refresh();
        },
    });
};

custom_ledger.fetch_field_options = function (frm) {
    frappe.call({
        method: "custom_ledger.custom_ledger.doctype.ledger_config.ledger_config.get_field_options",
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
