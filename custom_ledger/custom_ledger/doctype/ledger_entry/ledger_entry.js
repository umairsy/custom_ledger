// Copyright (c) 2026, Custom Ledger Contributors
// License: TBD. See license.txt

// "Create → Journal Entry / Stock Entry / Stock Reconciliation" from a
// submitted Ledger Entry. The target is opened pre-filled (amount chosen at
// click time) and completed by the user — ERPNext's own form drives the
// account/item/warehouse and validation. Shown only when ERPNext is installed.

frappe.ui.form.on("Ledger Entry", {
    refresh: function (frm) {
        if (frm.doc.docstatus !== 1) return;

        frappe.call({
            method: "custom_ledger.core.erpnext_integration.is_erpnext_installed",
            callback: function (r) {
                if (!r.message) return;
                ["Journal Entry", "Stock Entry", "Stock Reconciliation"].forEach(function (dt) {
                    frm.add_custom_button(
                        __(dt),
                        function () { custom_ledger_create_transaction(frm, dt); },
                        __("Create")
                    );
                });
            },
        });
    },
});

// Dialog: pick which amount to carry (and Dr/Cr for a Journal Entry), then open
// the pre-filled target.
function custom_ledger_create_transaction(frm, target_dt) {
    const is_journal = target_dt === "Journal Entry";

    const fields = [
        {
            fieldname: "amount_source",
            label: __("Amount From"),
            fieldtype: "Select",
            options: ["Delta", "Balance", "Value"].join("\n"),
            default: "Delta",
            reqd: 1,
            description: __("Delta {0} · Balance {1} · Value {2}", [
                format_number(frm.doc.delta),
                format_number(frm.doc.balance),
                format_number(frm.doc.value),
            ]),
        },
    ];
    if (is_journal) {
        fields.push({
            fieldname: "direction",
            label: __("Post As"),
            fieldtype: "Select",
            options: ["Debit", "Credit"].join("\n"),
            default: flt(frm.doc.delta) < 0 ? "Credit" : "Debit",
            reqd: 1,
        });
    }

    const dialog = new frappe.ui.Dialog({
        title: __("Create {0}", [__(target_dt)]),
        fields: fields,
        primary_action_label: __("Create"),
        primary_action: function (values) {
            dialog.hide();
            const amount = Math.abs(flt(frm.doc[values.amount_source.toLowerCase()]));
            custom_ledger_open_prefilled(frm, target_dt, amount, values.direction);
        },
    });
    dialog.show();
}

function custom_ledger_open_prefilled(frm, target_dt, amount, direction) {
    const reference = __("Custom Ledger: {0} ({1})", [frm.doc.name, frm.doc.ledger_config]);

    frappe.model.with_doctype(target_dt, function () {
        const doc = frappe.model.get_new_doc(target_dt);
        doc.posting_date = frm.doc.posting_date;

        if (target_dt === "Journal Entry") {
            doc.voucher_type = "Journal Entry";
            doc.user_remark = reference;
            const row = frappe.model.add_child(doc, "Journal Entry Account", "accounts");
            if (direction === "Credit") {
                row.credit_in_account_currency = amount;
            } else {
                row.debit_in_account_currency = amount;
            }
        } else if (target_dt === "Stock Reconciliation") {
            doc.purpose = "Stock Reconciliation";
            doc.remarks = reference;
            const row = frappe.model.add_child(doc, "Stock Reconciliation Item", "items");
            row.qty = amount;
        } else if (target_dt === "Stock Entry") {
            doc.stock_entry_type = "Material Receipt";
            doc.remarks = reference;
            const row = frappe.model.add_child(doc, "Stock Entry Detail", "items");
            row.qty = amount;
        }

        frappe.set_route("Form", target_dt, doc.name);
    });
}
