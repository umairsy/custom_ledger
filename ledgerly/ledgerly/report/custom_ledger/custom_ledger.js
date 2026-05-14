// Copyright (c) 2026, Ledgerly Contributors
// License: TBD. See license.txt

frappe.query_reports["Custom Ledger"] = {
    filters: [
        {
            fieldname: "ledger_config",
            label: __("Ledger Config"),
            fieldtype: "Link",
            options: "Ledger Config",
            reqd: 1,
            on_change: function () {
                // When the config changes, dimension filters need to refresh.
                // Frappe re-runs the report automatically; we hook in here
                // only if we ever need to mutate filter visibility.
                frappe.query_report.refresh();
            },
        },
        {
            fieldname: "from_date",
            label: __("From Date"),
            fieldtype: "Date",
        },
        {
            fieldname: "to_date",
            label: __("To Date"),
            fieldtype: "Date",
        },
        {
            fieldname: "source_name",
            label: __("Source Document"),
            fieldtype: "Data",
            description: __(
                "Optional. When set, the report shows opening and closing balances for this source only."
            ),
        },
        {
            fieldname: "group_by_source",
            label: __("Group by Source"),
            fieldtype: "Check",
            default: 0,
            description: __(
                "Show opening and closing balances for each source. Only takes effect when a specific Source Document is NOT picked."
            ),
        },
        // Dimension filter slots — five of them. When a Ledger Config is
        // selected, Frappe re-runs execute() but doesn't dynamically rename
        // filter labels. We keep these as generic dim_N filters; users
        // referencing a specific dimension can use them.
        {
            fieldname: "dim_1",
            label: __("Dimension 1"),
            fieldtype: "Data",
        },
        {
            fieldname: "dim_2",
            label: __("Dimension 2"),
            fieldtype: "Data",
        },
        {
            fieldname: "dim_3",
            label: __("Dimension 3"),
            fieldtype: "Data",
        },
        {
            fieldname: "dim_4",
            label: __("Dimension 4"),
            fieldtype: "Data",
        },
        {
            fieldname: "dim_5",
            label: __("Dimension 5"),
            fieldtype: "Data",
        },
    ],
};
