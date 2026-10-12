# Billing analytics

The two read-only analytics tools are now included in the main billing agent alongside the operational workflows. See WORKFLOWS.md for setup and behavior.

Start the application from the project directory:

```powershell
python app.py
```

Start Streamlit as usual. Existing Azure settings, chat history and invoice downloads
are reused. Startup adds operational ledger tables. No new packages are required.
The older app_analytics.py launcher remains compatible and exposes the same tools.

## Tools

- `billing_analysis`: invoice totals, discounts, tax, shipping, ledger refunds,
  net billed amounts, current product cost estimates, and top customers/products.
  Filters: `customer_id`, `order_id`, `date_from`, `date_to`; optional `top_n` (1–25).
- `billing_anomalies`: checks total/line/subtotal arithmetic, quantities, refund
  consistency, and prices against available dated history. Flags unusually large
  invoices and suggests reviews of refund causes, margin pressure and inventory.
  Same filters; optional `max_findings` (1–100) and `high_charge_threshold` (default 5000).

Both tools use a read-only SQLite snapshot and parameterized filters. Financial
totals include all selected invoices, independently of the existing SQL tool's
200-row response cap. More than 10,000 matching orders requires a narrower filter.
Dates are inclusive order dates; refund totals therefore refer to refunds on those
orders, not refunds processed during that period (the schema has no refund date).

Cancelled drafts are excluded from selections, and all drafts are excluded from financial totals. Costs use current item baseprice;
historical purchase costs are unavailable. Margin estimates exclude refunds,
tax, shipping and overhead. Currency uses invoice snapshots where available, falling
back to current configuration for legacy data. Mixed-currency selections are rejected;
use billing_statement for totals grouped by currency. Analytics shows face-value billing;
use billing_statement for credit notes, recorded payments and receivables.
Ledger entries do not prove payments occurred. Rules flag review candidates;
suggestions are not guarantees of savings and never execute changes.

Inventory suggestions are suppressed for customer/order-specific filters because
those filters omit other customers' demand. Even a global analysis covers only
products billed in the selected period, and needs a seasonality/demand review.

## Example chat requests

- Show the billing cost breakdown for all invoiced orders.
- Analyze billing for FAKE-CUST-0001.
- Break down invoice costs for order FAKE-ORD-0001.
- Find billing anomalies between 2026-04-01 and 2026-10-08.
- Suggest ways to reduce costs based on refunds, margins and inventory.

## Compatibility files

```text
app_analytics.py
agent/analytics_agent.py
mcp_server/server_analytics.py
mcp_server/tools/analytics_tools.py
ANALYTICS.md
```

These older extension filenames remain available for compatibility. The main server
now registers all eighteen tools. Both entry points share the operational prompt and
the same persistent transport lifecycle.

## Verification

Verified against a temporary copy of the seeded database: all 300 invoice totals,
50 excluded drafts, 60 ledger refunds, filter behavior and read-only connections.
The original seed produced no integrity anomaly flags. Injected total, line,
quantity, refund metadata and historical-price errors were detected.

The current real MCP integration discovers all eighteen tools and exercises SQL,
billing, receipts, statements and both analytics tools. AutoGen tests use replay
models. The operational upgrade was also checked on a temporary copy of the seeded
database; all original rows and the source database file were preserved.
