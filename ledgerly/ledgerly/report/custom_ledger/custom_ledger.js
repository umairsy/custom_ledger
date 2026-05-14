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
        {
            fieldname: "source_name",
            label: __("Source Document"),
            fieldtype: "Link",
            options: "",
            hidden: 1,
        },
        {
            fieldname: "dim_1",
            label: __("Dimension 1"),
            fieldtype: "Link",
            options: "",
            hidden: 1,
        },
        {
            fieldname: "dim_2",
            label: __("Dimension 2"),
            fieldtype: "Link",
            options: "",
            hidden: 1,
        },
        {
            fieldname: "dim_3",
            label: __("Dimension 3"),
            fieldtype: "Link",
            options: "",
            hidden: 1,
        },
        {
            fieldname: "dim_4",
            label: __("Dimension 4"),
            fieldtype: "Link",
            options: "",
            hidden: 1,
        },
        {
            fieldname: "dim_5",
            label: __("Dimension 5"),
            fieldtype: "Link",
            options: "",
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

        // --- Opening / Closing rows: amber band + bold. ---
        if (is_summary) {
            const text = value !== null && value !== undefined ? value : "";
            // Amber background spans the full cell via a block div.
            return (
                `<div style="background:#FFF3CD;border-top:1px solid #E6AC00;` +
                `border-bottom:1px solid #E6AC00;font-weight:600;` +
                `padding:3px 0;margin:0 -8px;padding-left:8px;">` +
                `${default_formatter(text, row, column, data)}</div>`
            );
        }

        // --- Delta column: signed, green for positive, coral for negative. ---
        if (column.fieldname === "delta" && value !== null && value !== undefined) {
            const num = parseFloat(value);
            if (!isNaN(num) && num !== 0) {
                const color = num > 0 ? "#0F6E56" : "#993C1D";
                const sign = num > 0 ? "+" : "";
                const formatted = frappe.format(Math.abs(num), { fieldtype: "Float", precision: 6 });
                return (
                    `<span style="color:${color};font-weight:600;font-variant-numeric:tabular-nums;">` +
                    `${sign}${num < 0 ? "−" : ""}${formatted}</span>`
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
            frappe.query_report.set_filter_value(fn, "");
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

            // Source Document filter — label and options reflect the source doctype.
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
                    frappe.query_report.set_filter_value(`dim_${i}`, "");
                }
            }
        },
    });
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

    // Toggle wrapper visibility based on hidden flag.
    if (filter.$wrapper) {
        filter.$wrapper.toggle(!filter.df.hidden);
    }

    // Re-render the control so updated options/label take effect.
    if (typeof filter.refresh === "function") {
        filter.refresh();
    }
}
