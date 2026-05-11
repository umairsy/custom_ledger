# Ledgerly

**Configurable custom ledgers for Frappe.** Define your own ledgers — like Stock Ledger or GL Entry — driven by field changes on any DocType, without writing code.

## Why Ledgerly?

In ERPNext, the Stock Ledger and General Ledger are powerful but **hardcoded**. If you want a similar audit trail for any other numeric field — say, the weight of a goat, the height of a sapling, the moisture content of a grain batch — you have to write a Frappe app from scratch.

Ledgerly fills that gap. Configure a *Ledger Config*, point it at a DocType and a numeric field, pick some dimension fields for reporting, and Ledgerly will:

- Capture a ledger entry every time the tracked value changes
- Maintain a running balance per source record
- Repost balances correctly when back-dated entries are inserted
- Give you a built-in report with opening / closing balances and dimensional filters

## Use case — goat-farm growth tracking

A goat-trading business wants to track each goat's weight over time. Today they can update weight on the Item master, but they lose history. With Ledgerly:

1. Configure a Ledger Config: source = `Item`, tracked field = `goat_weight` (a custom field), dimensions = `item_group`, `goat_breed`.
2. Every time someone updates `goat_weight`, a ledger entry is automatically created with the new value, the delta, and the running balance.
3. View the Ledgerly Report filtered by individual goat (SKU), breed, or warehouse.

Ledgerly is **domain-agnostic** — the goat example is just one. It works for any numeric field on any DocType.

## Status

This app is under active development. The current scaffold is the foundation; feature DocTypes (Ledger Config, Ledger Entry) and the engine ship in subsequent PRs.

- [x] App scaffold, CI, Semgrep
- [ ] Ledger Dimension child DocType
- [ ] Ledger Config DocType
- [ ] Ledger Entry DocType (submittable)
- [ ] Ledger engine (single field changes)
- [ ] Child-table sum support
- [ ] Back-dated reposting (background job)
- [ ] Cancellation handling
- [ ] Ledgerly Report
- [ ] Workspace (v15)
- [ ] ERPNext integration buttons (Stock Recon / Stock Entry / Journal Entry)
- [ ] Marketplace prep + v16 desktop icon

## Installation

### Prerequisites

- Frappe Bench (Frappe Framework v15)
- Python 3.10, 3.11, or 3.12

### Install on a local bench

```bash
cd ~/frappe-bench
bench get-app ledgerly https://github.com/<owner>/ledgerly
bench --site <your-site> install-app ledgerly
bench --site <your-site> migrate
```

### Install on Frappe Cloud

1. Push this repository to your GitHub account.
2. In Frappe Cloud, go to your bench → **Apps** → **Add App** → choose **GitHub** → select this repository.
3. Deploy. Frappe Cloud reads `pyproject.toml` to verify Frappe version compatibility.

## Compatibility

| Frappe version | Status |
| -------------- | ------ |
| v15            | ✅ Targeted (primary) |
| v16            | 🟡 Install path open; workspace/desktop icon support in a later PR |

## Development

Clone into a bench's `apps/` folder and install:

```bash
cd ~/frappe-bench/apps
git clone https://github.com/<owner>/ledgerly
cd ..
bench --site <your-site> install-app ledgerly
bench --site <your-site> migrate
```

Run the test suite:

```bash
bench --site <your-site> set-config allow_tests true
bench --site <your-site> run-tests --app ledgerly
```

## Continuous Integration

Every pull request runs:

- Unit tests on Python 3.10, 3.11, 3.12 against Frappe v15 (`.github/workflows/ci.yml`)
- Semgrep scan with the official Frappe security rules (`.github/workflows/semgrep.yml`)

## License

TBD — a formal open-source license will be selected before the first stable release.

## Contributors

Ledgerly Contributors
