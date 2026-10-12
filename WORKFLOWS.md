# Billing Agent workflows

This version keeps Python, Azure OpenAI, AutoGen, MCP, FastAPI, SQLite, Streamlit and ReportLab. It uses the existing chat layout and adds operational billing workflows to the normal `python app.py` entry point. Eighteen MCP tools are available; no separate analytics installation is required.

## Install or upgrade

1. Stop the API and Streamlit. Back up your existing database folder and local `.env`.
2. Extract the update ZIP into the project folder containing `app.py`, keeping its directory structure. The ZIP excludes `.env`, database files and generated invoices, so your local configuration and records are not replaced.
3. Keep your existing virtual environment and dependencies. No stack or dependency changes are required. For a fresh installation, install `requirements-lock.txt` and copy `.env.example` to `.env`, then enter your Azure credentials.
4. Start the API with `python app.py`. Startup runs the additive SQLite migration automatically. It creates new operational tables and indexes without deleting or rewriting existing orders.
5. In a second terminal, run `python -m streamlit run ui/streamlit_app.py`.

The older `python app_analytics.py` command remains compatible and now exposes the same workflow set. Do not run both launchers on the same port. You do not need to reseed existing data. For an empty demonstration installation, use `python -m database.seed`, or the larger `python generate_seed.py` dataset.

## Available work

| Workflow | What the agent can do |
| --- | --- |
| Customer records | Create customers and update names, company and email after confirmation. |
| Draft orders | Create estimates, replace the full item list, apply promotions, cancel unwanted drafts, and confirm placement. Stock is deducted only on placement. |
| Invoices | Preserve issued line amounts, snapshot customer contact and currency, assign a default due date 30 days from placement, generate an updated PDF with ledger balances. |
| Payment terms | Set or extend a placed invoice's due date with a reason and confirmation. |
| Receipts | Record partial or full payments, enforce unique external references, and reverse incorrect receipt entries. |
| Credits and refunds | Issue immutable monetary credit notes; retain the original one-refund-per-order ledger workflow. Combined adjustments cannot exceed invoice total. |
| Receivables | Show individual invoice balances, customer statements, overall receivables and aging buckets, grouped by currency. |
| Reconciliation | Compare billed amounts, recorded receipts, credits and ledger refunds. Show receipt and adjustment history for an invoice. |
| Disputes | Open and resolve billing disputes, retaining the complaint and resolution. |
| Customer conversations | Track support cases, notes, escalation and resolution; distinguish customer claims from staff-verified facts. See CUSTOMER_CONVERSATIONS.md for 27 conversation scenarios and the case workflow. |
| Collection follow-up | Prepare an overdue reminder draft. Open disputes, missing due dates and settled invoices suppress reminders. |
| Analysis | Analyze invoice face values, current-cost estimates, billing anomalies and evidence-based cost-review suggestions. |
| Audit | Record successful transactional tool changes in an append-only audit table. Failed transactions roll back their changes and audit inserts. |

## Example conversations

- “Show the outstanding balance and payment history for order ORDER1.”
- “Show CUST001's statement and overdue invoices.”
- “Record a USD 50 payment for ORDER1, received on 2026-10-11 by bank transfer. Payment ID PAY-1001, external reference BANK-ABC-1001.”
- “Reverse payment PAY-1001 because it was matched to the wrong invoice.”
- “Issue a USD 10 credit for ORDER1, credit ID CN-1001, for an agreed price adjustment.”
- “Extend ORDER1's due date to 2026-11-15 because the customer requested revised terms.”
- “Open dispute DIS-1001 for ORDER1 because the customer reports an incorrect quantity.”
- “Resolve dispute DIS-1001. The customer accepted the invoice after reviewing the delivery record.”
- “Draft a payment reminder for ORDER1.”
- “Replace the draft's items with two ITEM002 units.”
- “Cancel the draft because it is a duplicate request.”
- “Show receivables aging across all customers, grouped by currency.”
- “Review billing anomalies and possible cost improvements.”

Use IDs that exist in your own database. The agent must show proposed confirmed changes and obtain your explicit approval before committing them. Tool arguments provide an additional confirmation gate; this is an operator workflow, not a separate human approval or role-based authorization service. Draft creation itself does not require placement confirmation.

## Balance rules

The local adjusted invoice total equals original charged amount minus credit notes minus the existing ledger refund amount. Balance due is the positive difference between that adjusted total and non-reversed recorded payments. If payments exceed the adjusted total after a credit/refund, the difference is reported separately as customer credit to review.

New payments cannot exceed the current local balance. A credit note does not rewrite original invoice taxes or line amounts. Credits and legacy ledger refunds must not be entered for the same adjustment. Receipt reversals correct erroneous ledger entries and do not refund customers. Receipt and credit amounts are stored as integer cents and calculated with Decimal; original schema money fields remain compatible.

The statement tool totals every matched invoice before paginating detail rows. Different currencies have separate totals. Aging uses current local balances and a chosen aging date; it is not a reconstruction of an earlier accounting period. Known due dates have current, 1-30, 31-60, 61-90 and over-90 day buckets. Missing legacy due dates use a separate unknown bucket.

## Existing data

Historical payment settlement cannot be inferred from `orders.charged_price`. Imported invoices without receipt history may appear unpaid in this local ledger even if they were paid elsewhere. Reconcile known receipts before using these balances for collections. Older invoices without a currency snapshot use the current billing currency and are marked as inferred; missing due dates are not fabricated.

Existing refunds are treated as invoice adjustments, not proof of money movement. Existing historical invoice contact details cannot be reconstructed; contact snapshots are captured for newly placed invoices. Cancellation retains draft records and requested quantities without restocking because drafts never reserved inventory.

## Speed and reliability

The API warms the MCP process once, reuses the Azure client and tool connection, and caches fixed tool schemas. Each message gets a fresh model conversation context. Invoice downloads reuse the warmed tool connection. Streamlit reuses its HTTP client without changing its appearance. Specialized statement tools avoid repeated model-led SQL lookups, and indexed queries aggregate before pagination. Billing data and completed financial results are not cached as fresh facts.

Draft placement rejects changed prices or charges so an operator can review new totals before confirming. SQLite write transactions serialize changes to prevent concurrent overpayment, excessive adjustments or overselling. Request IDs and financial record IDs help avoid duplicate writes. A timed-out request may have committed before its final model response; inspect the order before sending another mutation. The API remains one worker with serialized agent turns, appropriate for this local operator console. Azure generation latency still applies.

## Boundaries

This is a local billing operations assistant. It records receipts and refund adjustments but does not charge cards, call a bank, verify settlement, or send refunds. It drafts reminders but does not send email. It does not implement subscriptions/automatic recurring charges, inventory returns, multi-user roles, multi-company accounting, exchange rates, or jurisdiction-specific tax filing. Audit records describe tool changes but do not establish authenticated individual staff identity or tamper-proof external storage. Legacy operations are not backfilled into the audit trail.

## Validation

Run `python -m pip install -r requirements-dev.txt`, then `python -m pytest -q`. Tests use temporary databases. New checks cover receipts and reversals, duplicate references, concurrent overpayment prevention, currency grouping, credit/refund limits, cancellation, dispute suppression, legacy data, snapshots and audit rollback. MCP integration discovers all eighteen tools and exercises the new ledger workflows. Model tests use replay responses; live Azure credentials and latency must be verified in your environment.
