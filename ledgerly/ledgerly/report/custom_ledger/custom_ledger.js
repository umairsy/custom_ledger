// Copyright (c) 2026, Ledgerly Contributors
// License: TBD. See license.txt

frappe.query_reports["Custom Ledger"] = {
    // ----------------------------------------------------------------
    // Filters — static shell. Dynamic Link options and labels for
    // source_name and dim_1..5 are patched in update_dynamic_filters()
    // whenever the ledger_config filter changes.
    // ----------------------------------------------------------------
    filters: [
        {
            fieldname: "ledger_config",
            label: __("Ledger Config"),
            fieldtype: "Link",
            options: "Ledger Config",
            reqd: 1,
            on_change: function () {
                update_dynamic_filters();
            },
        },
        {
            fieldname: "from_date",
            label: __("From Date"),
            fieldtype: "Date",
            default: frappe.datetime.month_start(),
        },
        {
            fieldname: "to_date",
            label: __("To Date"),
            fieldtype: "Date",
            default: frappe.datetime.get_today(),
        },
        // source_name and dim_1..5 start hidden; updated by update_dynamic_filters().
        // MultiSelectList: get_data reads filter.df.options (set dynamically to the
        // linked doctype) so autocomplete always queries the correct doctype.
        {
            fieldname: "source_name",
            label: __("Source Document"),
            fieldtype: "MultiSelectList",
            get_data: function (txt) {
                return _get_link_options("source_name", txt);
            },
            hidden: 1,
        },
        {
            fieldname: "dim_1",
            label: __("Dimension 1"),
            fieldtype: "MultiSelectList",
            get_data: function (txt) {
                return _get_link_options("dim_1", txt);
            },
            hidden: 1,
        },
        {
            fieldname: "dim_2",
            label: __("Dimension 2"),
            fieldtype: "MultiSelectList",
            get_data: function (txt) {
                return _get_link_options("dim_2", txt);
            },
            hidden: 1,
        },
        {
            fieldname: "dim_3",
            label: __("Dimension 3"),
            fieldtype: "MultiSelectList",
            get_data: function (txt) {
                return _get_link_options("dim_3", txt);
            },
            hidden: 1,
        },
        {
            fieldname: "dim_4",
            label: __("Dimension 4"),
            fieldtype: "MultiSelectList",
            get_data: function (txt) {
                return _get_link_options("dim_4", txt);
            },
            hidden: 1,
        },
        {
            fieldname: "dim_5",
            label: __("Dimension 5"),
            fieldtype: "MultiSelectList",
            get_data: function (txt) {
                return _get_link_options("dim_5", txt);
            },
            hidden: 1,
        },
    ],

    // ----------------------------------------------------------------
    // onload — called once after the report UI is ready.
    // If the report was opened with a pre-set ledger_config (e.g. via
    // the "View Report" button), trigger the dynamic filter update now.
    // ----------------------------------------------------------------
    onload: function (report) {
        const config = report.get_filter_value("ledger_config");
        if (config) {
            update_dynamic_filters();
        }
    },

    // ----------------------------------------------------------------
    // formatter — applies visual treatment to specific row types and
    // column values without introducing external CSS.
    // ----------------------------------------------------------------
    formatter: function (value, row, column, data, default_formatter) {
        const is_summary = data && (data._row_type === "opening" || data._row_type === "closing");

        // --- Opening / Closing rows: bold on label and numeric cells only. ---
        // No background, no borders — these rows look like regular data rows
        // but with bold text on the cells that carry information.
        if (is_summary) {
            const text = value !== null && value !== undefined ? value : "";
            const bold_cols = ["source_name", "opening", "delta", "balance"];
            if (bold_cols.includes(column.fieldname)) {
                return `<span style="font-weight:600;">${default_formatter(text, row, column, data)}</span>`;
            }
            return default_formatter(text, row, column, data);
        }

        // --- Delta column: signed, green for positive, coral for negative. ---
        if (column.fieldname === "delta" && value !== null && value !== undefined) {
            const num = parseFloat(value);
            if (!isNaN(num)) {
                const precision = column.precision != null ? column.precision : 2;
                if (num === 0) {
                    return (
                        `<span style="color:#6c757d;font-variant-numeric:tabular-nums;">` +
                        `${num.toFixed(precision)}</span>`
                    );
                }
                const color = num > 0 ? "#0F6E56" : "#993C1D";
                const sign = num > 0 ? "+" : "−";
                return (
                    `<span style="color:${color};font-weight:600;font-variant-numeric:tabular-nums;">` +
                    `${sign}${Math.abs(num).toFixed(precision)}</span>`
                );
            }
        }

        // --- Source Document column: clickable link for data rows. ---
        if (column.fieldname === "source_name" && data && data.source_doctype && data._row_type === "data") {
            const route = frappe.router.slug(data.source_doctype);
            const name = encodeURIComponent(data.source_name || "");
            return `<a href="/app/${route}/${name}">${data.source_name || ""}</a>`;
        }

        // --- Narration: italic, muted, with full text in title tooltip. ---
        if (column.fieldname === "narration" && value) {
            return (
                `<span style="color:#6c757d;font-style:italic;" title="${frappe.utils.escape_html(value)}">` +
                `${frappe.utils.escape_html(value)}</span>`
            );
        }

        return default_formatter(value, row, column, data);
    },
};

// ----------------------------------------------------------------
// Dynamic filter management
// ----------------------------------------------------------------

function update_dynamic_filters() {
    const config = frappe.query_report.get_filter_value("ledger_config");

    // No config — hide and clear all dynamic filters.
    const dynamic = ["source_name", "dim_1", "dim_2", "dim_3", "dim_4", "dim_5"];
    if (!config) {
        dynamic.forEach((fn) => {
            _set_filter(fn, { hidden: 1 });
            frappe.query_report.set_filter_value(fn, []);
        });
        return;
    }

    frappe.call({
        method: "ledgerly.ledgerly.doctype.ledger_config.ledger_config.get_config_meta",
        args: { name: config },
        callback: function (r) {
            if (!r.message) return;
            const meta = r.message;

            // Update page title to the ledger's display name.
            frappe.query_report.page.set_title(meta.ledger_name || __("Custom Ledger"));

            // Source Document filter — label reflects the source doctype; options
            // stores the doctype name so get_data can autocomplete against it.
            _set_filter("source_name", {
                label: __(meta.source_doctype),
                options: meta.source_doctype,
                hidden: 0,
            });

            // Dimension filters — show only dims defined in this config.
            for (let i = 1; i <= 5; i++) {
                const dim = meta.dimensions[i - 1];
                if (dim) {
                    _set_filter(`dim_${i}`, {
                        label: __(dim.label || dim.link_doctype),
                        options: dim.link_doctype,
                        hidden: 0,
                    });
                } else {
                    _set_filter(`dim_${i}`, { hidden: 1 });
                    frappe.query_report.set_filter_value(`dim_${i}`, []);
                }
            }
        },
    });
}

/**
 * Return autocomplete options for a MultiSelectList filter.
 * Reads filter.df.options (set by update_dynamic_filters) to know which
 * doctype to query — this is the convention that ties dynamic doctype
 * assignment to the get_data callback.
 */
function _get_link_options(fieldname, txt) {
    const filters = frappe.query_report && frappe.query_report.filters;
    if (!filters) return [];
    const filter = filters.find((f) => f.df && f.df.fieldname === fieldname);
    const doctype = filter && filter.df && filter.df.options;
    if (!doctype) return [];
    return frappe.db.get_link_options(doctype, txt);
}

/**
 * Patch a filter's docfield properties and re-render it.
 * Works by walking frappe.query_report.filters (array of control objects).
 */
function _set_filter(fieldname, props) {
    if (!frappe.query_report || !frappe.query_report.filters) return;

    const filter = frappe.query_report.filters.find(
        (f) => f.df && f.df.fieldname === fieldname
    );
    if (!filter) return;

    Object.assign(filter.df, props);

    if (filter.$wrapper) {
        filter.$wrapper.toggle(!filter.df.hidden);
        // Force label text update in the DOM — filter.refresh() alone does
        // not always re-render the <label> element in Frappe v15 reports.
        if (props.label) {
            filter.$wrapper.find(".control-label").text(__(filter.df.label));
        }
    }

    // Re-render the control so updated options/label take effect.
    if (typeof filter.refresh === "function") {
        filter.refresh();
    }
}
