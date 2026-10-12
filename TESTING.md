# Verification of billing workflows and customer conversations

Verified on Windows with Python 3.13 using isolated SQLite databases.

- 81 distinct automated tests passed across the full run and a targeted follow-up check.
- Existing SQL restrictions, stock transactions, promotions, refunds, API idempotency,
  conversation isolation, invoice attachments and Streamlit chat behavior were checked.
- New tests cover partial receipts, reversal and retry behavior, external reference
  uniqueness, concurrent overpayment/adjustment limits, credits, statements, aging,
  currency snapshots, customer updates, cancellation, disputes, audit rollback and
  changed quote protection.
- Real MCP integration checks discovery of eighteen tools and exercises ledger and support-case tools.
- AutoGen tool/reflection tests use deterministic replay responses, not live Azure.
- An additive migration on a copy of the existing database preserved every original
  row in all nine original tables. Foreign-key checks passed after repeated migration.
- The statement reconciled all 300 seeded invoices even with its detail page limited
  to one invoice; one local measurement was 0.0247 seconds. This excludes model latency.
- The seeded database file's SHA-256 remained unchanged by verification.

The October 12, 2026 full run had 80 passing tests and one Streamlit startup timeout
at the test's 15-second limit. The unchanged UI test passed separately in 8.61 seconds.
Tests used a writable workspace temporary folder. Windows asyncio also required
local loopback network access in the test sandbox.

Live Azure inference was not attempted: no real Azure credentials were provided.
Fill the five Azure fields in your local .env and restart the
API and Streamlit processes to use your deployment. A configured health status
checks settings only; it does not verify Azure access.

The suite reports third-party deprecation warnings.
They do not affect these test results. PDF tests check generation and ownership;
they do not certify tax/legal compliance.

## Customer conversation update

Twelve support-case tests cover ownership, linked-order constraints, explicit confirmation,
idempotent event retries, conflicting IDs, state transitions, verified resolution,
reopening, stale/concurrent updates, pagination, category validation and append-only
audited history. They also check that a payment claim or case resolution cannot create
a receipt. Together with the 21 operational tests, the focused run passed all 33 tests.

On October 12, 2026, repeated additive migration on a fresh copy again preserved every
original row and passed foreign-key checks. All 300 invoices reconciled to USD 123,943.19;
the source database remained unchanged. The local statement query took 0.1132 seconds
in this run, excluding model latency. This is a measurement, not a latency guarantee.

CUSTOMER_CONVERSATIONS.md provides 27 scenarios for live Azure acceptance testing.
Prompt guidance alone cannot guarantee every conversation or model response. No additional
model-routing call was added; longer prompt text may affect Azure latency and token usage.
