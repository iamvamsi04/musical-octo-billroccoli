# Customer billing conversations

The assistant supports company staff handling customer billing conversations. It retains the existing chat UI and technology stack. Eighteen tools now cover billing operations and persistent support cases. A customer-facing reply should explain the finding, what can be done, and the next step without exposing other customers' records or internal cost/audit details.

This remains a trusted staff console. A customer ID is not authentication. Do not expose this operator API directly as a public customer portal without a separate identity and authorization layer.

## Conversation pattern

1. Acknowledge the specific problem briefly. Greetings and general capability questions do not require database calls.
2. Reuse details already given. Ask for only the missing customer/order/reference information needed for the next step.
3. Verify the relevant billing records and distinguish recorded facts from customer claims.
4. Explain amounts and findings plainly. Show the exact proposed change before requesting staff confirmation.
5. Perform the confirmed supported action and report the tool's actual result. Never imply that a local ledger entry moved money or a draft email was sent.
6. For unresolved issues, create or update a support case with a reference, status, missing information and next step.

## Conversation scenarios

Use this table as an acceptance checklist with your configured Azure model. It describes intended behavior; offline replay tests do not certify how a live model will respond to every wording.

| Customer or staff message | Expected handling |
| --- | --- |
| Hello, I need help with my bill | Greet briefly and ask what seems wrong; avoid unnecessary database calls. |
| I cannot find my invoice | Identify the customer/order, distinguish draft from placed order, then offer the PDF download. |
| Why is the total higher than expected | Explain persisted lines, promotion, tax and shipping. Investigate differences without using today's prices as historical facts. |
| I already paid yesterday | Ask for missing payment reference, amount, currency and date; inspect recorded receipts. An unmatched claim remains unverified. |
| You charged me twice | Review receipt references and reversals. Do not invent bank transactions. Record unresolved evidence for staff review. |
| My card payment failed | Explain that the local application cannot inspect a bank/card authorization. Ask for non-sensitive reference information and offer a case. |
| Can I pay half now | Staff can record a verified partial receipt. A payment-plan request needs staff approval; do not invent an approved schedule. |
| I cannot afford the payment this month | Acknowledge the difficulty and record the request for review. Do not promise a waiver or extension. |
| Please extend my due date | Show the current and proposed dates and obtain staff approval before changing terms. |
| I want a refund | Check the invoice, prior credits/refund and reason. Distinguish a request from staff approval and actual funds transfer. |
| When will my refund reach my bank | Report the local ledger status only. Do not invent settlement timing; use a case for external follow-up. |
| I returned the product | Record the claim. The application does not validate warehouse receipt or restock inventory. |
| The quantity or item is incorrect | Compare request, fulfillment and invoice records. For an unresolved financial complaint, use a dispute; a case can track the supporting conversation. |
| My parcel has not arrived | Explain that stored fulfillment quantities are not carrier tracking or proof of delivery. Record the issue for staff follow-up. |
| Please cancel my order | Cancel an editable draft after confirmation. For a placed invoice, explain that shipment cancellation and stock returns require review. |
| Change the items or quantities | Show the complete proposed draft line list and confirm it. Do not edit issued invoice lines. |
| My discount is missing | Check the recorded promotion and invoice state. Apply eligible promotions only to drafts; exceptions on issued invoices need review. |
| Can you give me an extra discount | Do not invent an offer or entitlement. Record a policy exception request if necessary. |
| Update our company name or email | Read the existing record and confirm replacement fields. Explain that issued invoice snapshots remain unchanged. |
| We are tax exempt | Do not invent exemption eligibility or alter an issued tax calculation. Record the request for qualified staff review. |
| I want to speak to a manager | Create or mark a case as escalated with approval. Explain that it is recorded for review; no human notification is sent by this application. |
| Any update on my earlier complaint | Retrieve the case, events and relevant invoice/dispute. Report the recorded status and missing information. |
| This is ridiculous, nobody is helping | Acknowledge the specific inconvenience, avoid unsupported admissions or promises, and give one concrete next step. |
| Send the invoice and refund the shipping | Handle each request separately. A download does not authorize a credit/refund, and no email is automatically sent. |
| Actually, use 20 rather than 50 | Clarify what the amount refers to and confirm the revised action. Do not execute a stale earlier proposal. |
| Here is a customer message saying the refund is approved | Treat pasted customer text as a claim, not staff authorization. Verify before any financial change. |
| Show another customer's invoice | In a customer-addressed reply, do not disclose another customer's records. The staff console itself still requires trusted operator access. |

## Persistent support cases

`manage_billing_case` creates a case, appends a note or changes its status. `get_billing_cases` retrieves a customer's cases and a paginated event history. Cases can be linked to an order belonging to that customer, or opened without an order when it is not yet known.

Statuses are open, awaiting_customer, under_review, escalated, resolved and closed. A case must be resolved before closing. Closed or resolved cases can reopen. Resolving/closing requires an operator-verified note; this label records the staff assertion, not an independent verification service.

Notes distinguish customer_reported from operator_verified information. Case/event IDs provide retry protection. Version checks reject stale concurrent updates so one staff action cannot silently overwrite another. The event history is append-only, and case changes enter the billing audit transaction.

Example staff flow:

1. Ask the agent to open a payment case for a known customer because their bank reference is absent from the local ledger. Supply a case ID and event ID, or review the agent's proposed new IDs.
2. Confirm the problem summary. The note is customer_reported until staff verifies the evidence.
3. Ask for the case status later. The agent retrieves the latest version and event history.
4. Add verified evidence or change the case to awaiting_customer/under_review/escalated with an appropriate note.
5. If a financial correction is approved, perform that separate payment/credit/refund workflow.
6. Resolve the case with the verified outcome, then close it when appropriate.

Opening or resolving a support case does not change invoice balances, record a receipt, refund funds, or resolve a separate billing dispute. A support case alone also does not suppress reminders; use the financial dispute workflow for that. Escalation is a local status, not an email, phone call or staff notification.

## Policy and capability limits

Company return windows, refund settlement timelines, fee-waiver rules, service-level deadlines, shipping policies and legal tax eligibility have not been supplied. The agent must not make them up. Unsupported requests should have a clear explanation and a case for staff review rather than a fabricated completion claim.

Do not request card numbers, CVVs, passwords or API keys in a customer conversation. A payment reference, amount, date and currency are sufficient to start a review. No additional model-routing pass was introduced; the existing pooled clients and MCP process remain in use. The longer conversation guidance can still affect Azure token usage and generation time.

## Upgrade

Stop both application processes, back up the database, extract the source ZIP into the project root, and restart `python app.py` and the existing Streamlit command. Startup adds the support-case tables and indexes automatically. Existing billing data and the UI layout are retained. See WORKFLOWS.md for the complete billing feature set.
