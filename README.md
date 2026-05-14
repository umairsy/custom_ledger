# Ledgerly

**Configurable custom ledgers for Frappe.** Define your own ledgers — like Stock Ledger or GL Entry — without writing code. Drive entries from field changes on any DocType, or from transactions feeding a running balance.

## Why Ledgerly?

In ERPNext, the Stock Ledger and General Ledger are powerful but **hardcoded**. If you want a similar audit trail for any other quantity — the weight of a goat, the credit balance of a customer, the budget burn of a project — you have to write a Frappe app from scratch.

Ledgerly fills that gap. Pick a Ledger Type, configure a Ledger Config, and Ledgerly will:

- Capture a ledger entry every time the tracked quantity changes
- Maintain a running balance, scoped to each source record
- Repost balances correctly when back-dated entries are inserted
- Give you a built-in report with opening / closing balances and dimensional filters

## Ledger Types

Ledgerly supports multiple ledger patterns through a **Ledger Type** selector on each Ledger Config:

| # | Ledger Type | Status | What it does |
|---|---|---|---|
| 1 | **Track changes to a field** | Shipped | Watches a single numeric field on a source DocType (or a sum across its child rows). Every change creates an entry. Use cases: goat weight, vehicle odometer, employee rating. |
| 2 | **Track balance from transactions** | In progress | Watches multiple feeder DocTypes. Some fields add to a balance; others deduct. Use cases: customer credit balance, gift cards, loyalty points. |
| 3 | Stock-Ledger-style (qty + value) | Future | Quantity and value tracked together, like ERPNext's Stock Ledger. |
| 4 | GL-style (debit + credit) | Future | Double-entry posting. |

## Use case 1: Goat-farm growth tracking (Track changes to a field)

1. Add a custom field `goat_weight` (Float) to Item.
2. Add a custom field `weight_measurement_date` (Date or Datetime) to Item.
3. Create a Ledger Config: type = `Track changes to a field`, source = `Item`, tracked field = `goat_weight`, posting date field = `weight_measurement_date`, dimensions = `item_group`, `goat_breed`.
4. Every time someone updates `goat_weight` on an Item, a Ledger Entry is automatically created with the new value, the delta vs prior, and a running balance per goat.
5. View the Ledgerly Report (coming in PR #7), filtered by individual goat, breed, or warehouse.

## Use case 2: Customer credit balance (Track balance from transactions — in progress)

1. Add a custom DocType `Credit Top-Up` with `customer` (Link to Customer) and `credits_purchased` (Currency).
2. Add a custom field `credits_used` (Currency) to Sales Invoice.
3. Create a Ledger Config: type = `Track balance from transactions`, balance carrier = `Customer.credit_balance`, ADD source = `Credit Top-Up.credits_purchased`, DEDUCT source = `Sales Invoice.credits_used`.
4. Each customer's `credit_balance` is computed live from their feeder transactions. The Ledgerly Report shows opening balance, every top-up and usage, and closing balance per customer.

## Status — progress and roadmap

### Completed (PRs #1–#6)
- App scaffold, CI, Semgrep, Frappe Cloud install
- Ledger Dimension (child DocType for declaring reporting dimensions)
- Ledger Config (with dynamic field selectors, child-table mode, posting datetime config, progressive disclosure)
- Ledger Entry (submittable, indexed, 5 dimension columns, idempotent via change signatures)
- "Track changes to a field" engine — hooked into every doc save; auto-creates entries on tracked-field changes; cached active-config lookup for near-zero per-save cost
- Ledger Type field with backfill for existing configs
- `after_migrate` cache clear — fixes the "needed to re-save config after deploy" bug for all future deploys

### In progress / next up
- **PR #7:** Ledgerly Report — from-date, to-date, opening, closing, dimensional columns. Type-agnostic (works for both ledger types).
- **PR #8:** "Track balance from transactions" config — new schema fields (balance carrier, ADD/DEDUCT sources), validation, client script, all guarded behind the new ledger type.
- **PR #9:** "Track balance from transactions" engine — hooks into feeder DocTypes' `on_submit` / `on_cancel`, creates entries with positive/negative deltas scoped to the balance carrier.
- **PR #10:** Back-dated reposting — reorders balances correctly when an entry is inserted between two existing entries. Background job.
- **PR #11:** Workspace + onboarding — sidebar shortcuts and a guided "create your first ledger" flow for new users.
- **PR #12:** ERPNext integration buttons (Stock Recon / Journal Entry from a Ledger Config), cancellation propagation, README polish, marketplace prep.

## Installation

### Prerequisites
- Frappe Bench (Frappe Framework v15)
- Python 3.10, 3.11, or 3.12

### Install on a local bench

    cd ~/frappe-bench
    bench get-app ledgerly https://github.com/<owner>/ledgerly
    bench --site <your-site> install-app ledgerly
    bench --site <your-site> migrate

### Install on Frappe Cloud

1. Push this repository to your GitHub account.
2. In Frappe Cloud, go to your bench → **Apps** → **Add App** → choose **GitHub** → select this repository.
3. Deploy.

## Compatibility

| Frappe version | Status |
| -------------- | ------ |
| v15            | Targeted (primary) |
| v16            | Install path open; workspace/desktop icon support in PR #11 |

## Development

Run the test suite:

    bench --site <your-site> set-config allow_tests true
    bench --site <your-site> run-tests --app ledgerly

## License

TBD — a formal open-source license will be selected before the first stable release.

## Contributors

Ledgerly Contributors
