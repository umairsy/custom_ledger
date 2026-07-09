# Custom Ledger

[![Frappe v16](https://img.shields.io/badge/Frappe-v16-blue.svg)](https://frappeframework.com/)
[![Frappe v15](https://img.shields.io/badge/Frappe-v15-blue.svg)](https://frappeframework.com/)

### Configurable ledgers for any DocType — no code required

*Turn changes on any Frappe/ERPNext DocType into a proper ledger, with running balances, an opening/closing report, and an analytics dashboard. You describe what to track in a Ledger Config; Custom Ledger generates everything else.*

[Quick Start](#quick-start) • [User Manual](USER_MANUAL.md) • [Ledger Types](#ledger-types) • [How it works](#how-it-works)

---

## Why Custom Ledger

ERPNext's Stock Ledger and General Ledger are powerful, but they're hardcoded. If you want the same kind of dated, auditable, running-balance history for anything else — a member's weight, a customer's prepaid credit, a project's budget burn — you normally have to build a Frappe app from scratch.

Custom Ledger closes that gap. Define a **Ledger Config**, and it automatically maintains the entries, the report, the dashboard, and a per-record drill-in button. Add a new kind of ledger by creating a config, never by writing code.

## Features

- **Two ledger types** — track a single field as it changes, or maintain a running balance fed by multiple transaction types.
- **Automatic ledger entries** — submitted, immutable, with value, delta, and running balance per entry.
- **Custom Ledger report** — opening balance, every movement, closing balance, color-coded deltas, narration, and dimensional columns driven by your config.
- **Auto-generated dashboard** — closing balance, net change, totals, record count, a balance-over-time chart, and group breakdowns, all filterable.
- **View Ledger button** — one click from any source record to its pre-filtered ledger.
- **Dimensions** — slice reports and charts by any link fields you nominate (diet plan, trainer, warehouse, item group, etc.).
- **Config-driven throughout** — the report and dashboard adapt to each config automatically; there is no per-ledger code.

## Ledger Types

| Type | What it watches | Example |
| --- | --- | --- |
| **Track changes to a field** | A single numeric field on one DocType; every change logs an entry. | A gym member's weight over time. |
| **Track balance from transactions** | Multiple feeder DocTypes that add to or deduct from a balance held on a separate carrier DocType. | A customer's credit balance, fed by Credit Purchases and Invoices. |

## How it works

1. **Create a Ledger Config.** Pick a ledger type, the DocType(s) to watch, the numeric field, the posting date, and any dimensions.
2. **Custom Ledger captures changes.** For *Track changes to a field*, updating the tracked field creates an entry. For *Track balance from transactions*, submitting a feeder creates an entry and updates the carrier's balance.
3. **Read the ledger.** Open the Custom Ledger report or the dashboard, or click **View Ledger** on any record.

For step-by-step setup of both ledger types, see the [User Manual](USER_MANUAL.md).

## Requirements

- Frappe Framework v16
- Python 3.14

## Installation

### On a local bench

```bash
cd ~/frappe-bench
bench get-app custom_ledger https://github.com/umairsy/custom_ledger
bench --site <your-site> install-app custom_ledger
bench --site <your-site> migrate
```

### On Frappe Cloud

1. Push this repository to your GitHub account.
2. In Frappe Cloud, open your bench → **Apps** → **Add App** → **GitHub**, and select this repository.
3. Deploy. Frappe Cloud reads `pyproject.toml` to verify version compatibility.

## Quick Start

Track a single field as it changes:

1. Open **Ledger Config → New**.
2. Set **Ledger Type** to *Track changes to a field*.
3. Set **Source DocType** (e.g. *Gym Member*) and **Tracked Field** (e.g. *Weight*).
4. Set **Posting Date Field** (e.g. *weight_reading_date*).
5. Save, then update the tracked field on a record — a ledger entry appears automatically.
6. Open the **Custom Ledger** report (or click **View Ledger** on the record) to see opening balance, movements, and closing balance.

Maintain a running balance from transactions:

1. Add a read-only Currency field to the carrier DocType (e.g. *Credit Balance* on *Customer*).
2. Create a Ledger Config with **Ledger Type** = *Track balance from transactions*.
3. Set **Balance Carrier DocType** and **Balance Field**.
4. Add **Transaction Sources** — one row per feeder, each with an amount field, direction (ADD/DEDUCT), and the link field pointing at the carrier.
5. Submit a feeder — the carrier's balance updates and an entry is logged.

## Documentation

- [User Manual](USER_MANUAL.md) — full feature guide with both use cases, the report, and the dashboard.

## Compatibility

| Frappe version | Status | Branch |
| --- | --- | --- |
| v16 | Targeted (primary) | `version-16` (this branch) |
| v15 | Maintained | [`main`](https://github.com/umairsy/custom_ledger/tree/main) |

See [docs/VERSIONING.md](docs/VERSIONING.md) for the branch model and how changes are kept in sync across versions.

## Development

Run the test suite:

```bash
bench --site <your-site> set-config allow_tests true
bench --site <your-site> run-tests --app custom_ledger
```

Every pull request runs unit tests and a Semgrep scan against Frappe's security rules.

## License

To be finalized before the first stable release.

## Contributors

Custom Ledger Contributors
