# Custom Ledger — User Manual

Custom Ledger lets you turn changes on any DocType into a proper ledger — with running balances, an opening/closing report, and an analytics dashboard — without writing code. You describe what to track in a **Ledger Config**, and Custom Ledger does the rest.

This manual covers what Custom Ledger does and how to use each feature. It assumes you already have Custom Ledger installed on your Frappe/ERPNext site.

---

## Contents

- [Core concepts](#core-concepts)
- [Ledger types](#ledger-types)
- [Use case 1: Track changes to a field](#use-case-1-track-changes-to-a-field)
- [Use case 2: Track balance from transactions](#use-case-2-track-balance-from-transactions)
- [The Custom Ledger report](#the-custom-ledger-report)
- [The dashboard](#the-dashboard)
- [Ledger entries](#ledger-entries)
- [Viewing a ledger from a record](#viewing-a-ledger-from-a-record)
- [Field reference](#field-reference)

---

## Core concepts

Custom Ledger is built around four objects:

**Ledger Config** — the setup record. It says which DocType to watch, which numeric field to track, when each entry is dated, and what dimensions to slice by. One config defines one ledger.

**Ledger Entry** — an automatically created, submitted record representing one change. Each entry stores the value, the change (delta), the running balance at that point, the posting date/time, and the narration as it was at posting time.

**Custom Ledger report** — the ledger view of those entries: opening balance, each movement, closing balance, with filters.

**Dashboard** — six visuals summarizing a ledger: closing balance, net change, totals, record count, a balance-over-time chart, and breakdowns.

You never create Ledger Entries by hand. You create a Ledger Config once, and entries appear as the underlying records change.

---

## Ledger types

When you create a Ledger Config you pick a **Ledger Type**. This is the single most important choice — it determines how Custom Ledger captures changes.

| Ledger Type | What it watches | Example |
| --- | --- | --- |
| **Track changes to a field** | A single numeric field on one DocType. Every time the field changes, an entry is created. | A gym member's weight over time. A goat's weight. A vehicle's odometer reading. |
| **Track balance from transactions** | Multiple feeder DocTypes whose submitted records add to or deduct from a running balance held on a separate "carrier" DocType. | A customer's credit balance, topped up by Credit Purchases and drawn down by Invoices. |

Pick the one that matches your data:

- If the number you care about **lives on the record itself** and changes in place → *Track changes to a field*.
- If the number is a **balance that accumulates from separate transactions** → *Track balance from transactions*.

---

## Use case 1: Track changes to a field

**Scenario:** A gym tracks each member's weight. Every time a trainer updates a member's `Weight`, the gym wants a dated history with the gain/loss per reading and a running view of progress.

### Step 1 — Prepare the source DocType

Make sure the DocType you want to track (here, **Gym Member**) has:

- A numeric field for the value (here, **Weight** — Currency, Int, or Float).
- A date field for when the reading was taken (here, **Weight Reading Date**), if you want entries dated by the measurement rather than by when the record was saved.
- Optionally, a text field for notes (here, **Narration**).
- Optionally, link fields you want to slice reports by (here, **Diet Plan**, **Gym Trainer**).

### Step 2 — Create the Ledger Config

Open **Ledger Config → New**. Fill in:

- **Ledger Name** — a human-readable name, e.g. *Weight Tracking*.
- **Ledger Type** — *Track changes to a field*.
- **Is Active** — checked. (When unchecked, the config exists but creates no entries.)

In the **Source** section:

- **Source DocType** — the DocType whose field changes drive entries (e.g. *Gym Member*).
- **Tracked Field** — the numeric field whose changes are logged (e.g. *Weight*). Must be Currency, Int, or Float.
- **Track Value From** — usually *Field on document*. Choose *Sum across child rows* only if the value is a total across a child table.
- **Narration Field (optional)** — a text field on the source DocType. When set, a Narration column appears in the report showing this text for each entry. Must be Data, Small Text, Text, or Long Text.

In the **Posting Date & Time** section:

- **Posting Date Source** — choose *Field on source DocType* when the user-controlled measurement date matters (e.g. a weight reading date). Choose *Document modification time* for records that don't need retroactive dating.
- **Posting Date Field** — the Date/Datetime field that sets when each entry is effective (e.g. *weight_reading_date*).
- **Posting Time Field (optional)** — a Time field, only meaningful when the posting date field is a Date (not Datetime). If blank, time defaults to 00:00:00.

In the **Dimensions** section:

- Add a row per field you want to slice the report and dashboard by. Each row takes a **Dimension Fieldname** (e.g. *diet_plan*, *gym_trainer*), an optional **Label**, and the **Link DocType** it points to. Dimensions become filter and column options downstream.

Save.

### Step 3 — Watch entries appear

From now on, every time someone changes the **Weight** on a Gym Member and saves, Custom Ledger creates a submitted Ledger Entry with the new value, the delta versus the previous reading, and the running balance for that member. No further action needed.

---

## Use case 2: Track balance from transactions

**Scenario:** A business sells prepaid credits to customers. A customer's credit balance goes **up** when they buy credits (a *Credit Purchase*) and **down** when credits are consumed against an *Invoice*. The balance lives on the **Customer** record, but it's driven entirely by those two transaction types.

This is what *Track balance from transactions* is for: many feeder DocTypes, one balance carrier.

### Step 1 — Prepare the carrier DocType

The **carrier** is the DocType that holds the running balance — here, **Customer**. It needs a numeric field to display the balance in (here, **Credit Balance** — a read-only Currency/Float/Int field). Add it via Customize Form if it doesn't exist. It must be **read-only**: the balance is maintained by Custom Ledger, not edited by hand.

### Step 2 — Identify the feeder DocTypes

Each feeder is a transaction whose submission moves the balance:

- **Credit Purchase** — has an amount field (e.g. `credit_purchased`) and a link to the customer. This **adds** to the balance.
- **Invoice** — has an amount field (e.g. `credits_consumed`) and a link to the customer. This **deducts** from the balance.

Each feeder must have a Link field pointing back to the carrier (here, a `customer` link).

### Step 3 — Create the Ledger Config

Open **Ledger Config → New**:

- **Ledger Name** — e.g. *Customer Credit Balance*.
- **Ledger Type** — *Track balance from transactions*.
- **Is Active** — checked.

In the **Carrier & Sources** section:

- **Balance Carrier DocType** — the DocType that holds the running balance (e.g. *Customer*).
- **Balance Field** — the read-only numeric field on the carrier that displays the balance (e.g. *Credit Balance*).
- **Transaction Sources** — add one row per feeder. Each row defines:
  - **Source DocType** — the feeder (e.g. *Credit Purchase*, *Invoice*).
  - **Amount Field** — the numeric field whose value is the transaction amount (e.g. *credit_purchased*, *credits_consumed*).
  - **Direction** — *ADD* or *DEDUCT*.
  - **Carrier Link Field** — the Link field on the feeder that points at the carrier (e.g. *customer*).
  - **Posting Date Field** — a Date/Datetime field on the feeder.
  - **Posting Time Field (optional)** — a Time field, used when the posting date field is a Date.
  - **Child Table Field (optional)** — only if the amount lives on a child table row.
  - **Is Active** — uncheck to temporarily disable one source without deleting the row.

You can add as many sources as you need — two for the credits example, more for scenarios like loyalty points (top-up adds, redemption deducts, expiry deducts, refund adds).

Save.

### Step 4 — Submit feeders and watch the balance move

Entries are created when a feeder is **submitted** (not merely saved). Submit a Credit Purchase for *200* against customer *ABC*, and:

- A Ledger Entry is created, scoped to customer ABC, with a delta of +200.
- The **Credit Balance** field on the ABC Customer record updates to 200.

Submit an Invoice consuming credits, and the balance drops accordingly. Cancelling a feeder reverses its entry automatically, restoring the prior balance.

---

## The Custom Ledger report

The **Custom Ledger** report turns entries into a readable ledger. Open it from the awesome bar (search "Custom Ledger") or via the **View Ledger** button on a source record.

### Filters

Across the top:

- **Ledger Config** (required) — selects which ledger to view. This also determines which columns appear.
- **From Date** / **To Date** — the reporting window.
- **Source Document** — narrow to one specific record (e.g. one gym member, one customer). When set, the report shows opening and closing balances for that record.
- **Dimension 1/2/3** — filter by the dimensions configured on the ledger.

### What the report shows

When filtered to a single source document, the report shows a true ledger:

| Posting Date | Time | Source | Opening | Delta | Balance | Narration | Dimension |
| --- | --- | --- | --- | --- | --- | --- | --- |
| | | **Opening Balance** | 55.00 | 0.00 | 55.00 | | |
| 07-05-2026 | 00:00:00 | Ajith | 55.00 | +2.00 | 57.00 | Third entry | Diet 1 |
| 09-05-2026 | 00:00:00 | Ajith | 57.00 | −3.00 | 54.00 | Unwell | Diet 1 |
| 13-05-2026 | 00:00:00 | Ajith | 54.00 | +2.00 | 56.00 | Back to normal | Diet 1 |
| 16-05-2026 | 00:00:00 | Ajith | 56.00 | +4.00 | 60.00 | All well | Diet 1 |
| | | **Closing Balance** | 0.00 | 5.00 | 60.00 | | |

Notes on the columns:

- **Opening / Closing rows** appear when a single source document is selected, bracketing the movements in the window.
- **Delta** is colored — gains in green (e.g. +2.00), reductions in red (e.g. −3.00).
- **Narration** shows the note as it was at the time of each entry.
- The **Source column header** is named after the source DocType (e.g. "Gym Member"), not a generic label.
- **Dimension columns** (e.g. Diet Plan) appear automatically based on the ledger's configured dimensions.

You can use comparison operators in the numeric filters — e.g. `>5`, `<10`, `=324`, or a range like `5:10`.

---

## The dashboard

Each ledger gets an auto-generated dashboard titled **"&lt;Ledger Name&gt; — Dashboard"**. It needs no setup; it's generated from the same config.

### Controls

- **From Date** / **To Date** — the window.
- **Time Grain** — Day, and other granularities, for the trend chart.
- **Group By** — switch the chart's series between *Source Document* (per member/customer) and any configured dimension (e.g. *Diet Plan*).
- **Dimension filters** — narrow the whole dashboard by dimension values.

### Visuals

- **KPI strip** — Closing Balance, Net Change, Total In, Total Out, and Records (count of entries in the window).
- **Balance Over Time** — a line chart of the running balance, with one line per group (per member, or per dimension value, depending on Group By).
- **Breakdown by Group** — distribution of activity across groups.
- **Top Movers** — the records with the largest movements.
- Plus distribution and activity visuals.

Everything reacts to the filters, so you can answer questions like "how did weight trend across Diet Plan 1 vs Diet Plan 2 this month" by changing **Group By** and the date window.

---

## Ledger entries

A **Ledger Entry** is the atomic record Custom Ledger creates. You rarely open one directly, but it's useful to understand its anatomy:

- **Source** — the Ledger Config, the Source Document, and the Source DocType.
- **Posting** — Posting Date, Posting Time, and a combined **Posting Datetime** (the canonical ordering key, computed from date + time, shown with the site timezone).
- **Value** — the tracked field's value at posting time.
- **Delta** — the change versus the previous entry.
- **Running Balance** — the balance for this source/config slice, recomputed when reposting occurs.

Entries are submitted documents. They form the immutable history behind the report and dashboard.

---

## Viewing a ledger from a record

Any source record gets a **View Ledger** button at the top of its form. On a Gym Member record, for example, clicking **View Ledger** opens the Custom Ledger report pre-filtered to that member — so you go straight from "this person" to "this person's ledger" in one click.

This works for both ledger types: on a carrier record (e.g. a Customer), View Ledger opens the report scoped to that carrier's balance history.

---

## Field reference

### Ledger Config — common fields

| Field | Purpose |
| --- | --- |
| Ledger Name | Human-readable name for the ledger. |
| Ledger Type | *Track changes to a field* or *Track balance from transactions*. |
| Is Active | When unchecked, the config creates no entries. |

### Ledger Config — "Track changes to a field"

| Field | Purpose |
| --- | --- |
| Source DocType | The DocType whose field changes drive entries. |
| Tracked Field | The numeric field to log (Currency / Int / Float). |
| Track Value From | *Field on document* or *Sum across child rows*. |
| Narration Field | Optional text field surfaced as a report column. |
| Posting Date Source | *Field on source DocType* or *Document modification time*. |
| Posting Date Field | Date/Datetime field setting when an entry is effective. |
| Posting Time Field | Optional Time field. |
| Dimensions | Link fields used as report/dashboard dimensions. |

### Ledger Config — "Track balance from transactions"

| Field | Purpose |
| --- | --- |
| Balance Carrier DocType | The DocType that holds the running balance (e.g. Customer). |
| Balance Field | Read-only numeric field on the carrier that displays the balance. |
| Transaction Sources | One row per feeder DocType. |

### Transaction Source (one feeder)

| Field | Purpose |
| --- | --- |
| Source DocType | The feeder transaction DocType. |
| Amount Field | The numeric field carrying the transaction amount. |
| Direction | *ADD* or *DEDUCT*. |
| Carrier Link Field | Link field on the feeder pointing at the carrier. |
| Posting Date Field | Date/Datetime field on the feeder. |
| Posting Time Field | Optional Time field. |
| Child Table Field | Optional — set if the amount lives on a child table. |
| Is Active | Disable this one source without deleting the row. |

---

*Custom Ledger is config-driven: you describe the ledger once, and the report, dashboard, entries, and per-record buttons all follow automatically.*
