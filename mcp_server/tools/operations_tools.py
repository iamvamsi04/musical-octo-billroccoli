"""Operator billing workflows. No external money movement or message delivery."""
from contextlib import contextmanager
from datetime import date
from decimal import Decimal
import json
import re

from database.connection import connect, transaction
from database.ledger import account, accounts, cash, cents, iso_date, LEDGER_NOTE
from mcp_server.tools.billing_tools import (BillingError, tool_result, identifier, money,
    order_row, is_placed, totals, update_totals, price_for)


def confirm(confirmed):
    if confirmed is not True:
        raise BillingError('Show the proposed change and obtain explicit operator confirmation first.')


def text(value, name, maximum=2000):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise BillingError(f'{name} must contain 1-{maximum} characters.')
    return value.strip()


@contextmanager
def reading():
    conn = connect(readonly=True)
    try:
        conn.execute('BEGIN')
        yield conn
    finally:
        conn.close()


def ensure_customer(conn, customer_id):
    if not conn.execute('SELECT 1 FROM customers WHERE customer_id=?', (customer_id,)).fetchone():
        raise BillingError('Customer not found.')


@tool_result
def manage_customer(customer_id: str, name: str, company: str = '', email: str = '',
                    action: str = 'create', confirmed: bool = False) -> dict:
    """Create or update a customer after confirmation. Update replaces all contact fields; show them first.

    Existing issued invoice contact snapshots are preserved. Use SQL to look up a customer before editing.
    """
    confirm(confirmed)
    identifier(customer_id, 'customer ID')
    name = text(name, 'Name', 200)
    if not isinstance(company, str) or len(company) > 200:
        raise BillingError('Company must contain at most 200 characters.')
    if not isinstance(email, str) or len(email) > 200 or (email and not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email)):
        raise BillingError('Provide a valid email address or leave it empty.')
    with transaction() as conn:
        existing = conn.execute('SELECT * FROM customers WHERE customer_id=?', (customer_id,)).fetchone()
        if action == 'create':
            if existing:
                if (existing['name'], existing['company'] or '', existing['email'] or '') != (name, company, email):
                    raise BillingError('Customer ID exists with different details. Use update after confirmation.')
                return {'customer_id': customer_id, 'already_exists': True}
            conn.execute('INSERT INTO customers VALUES (?,?,?,?)', (customer_id, name, company, email))
        elif action == 'update':
            ensure_customer(conn, customer_id)
            conn.execute('UPDATE customers SET name=?,company=?,email=? WHERE customer_id=?', (name, company, email, customer_id))
        else:
            raise BillingError('Action must be create or update.')
    return {'customer_id': customer_id, 'name': name, 'company': company, 'email': email, 'action': action}


@tool_result
def manage_draft(order_id: str, customer_id: str, action: str, items: list[dict] | None = None,
                 reason: str = '', confirmed: bool = False) -> dict:
    """After confirmation, replace all lines of a draft or cancel it. action: replace_items or cancel.

    items is the complete desired list of item_code and integer quantity. Never edits issued invoices.
    Cancellation retains records for audit and does not restock since drafts never reserved stock.
    """
    confirm(confirmed)
    with transaction() as conn:
        existing_meta = conn.execute('SELECT status FROM order_details WHERE order_id=?', (order_id,)).fetchone()
        if existing_meta and existing_meta['status'] == 'cancelled' and action == 'cancel':
            owner = conn.execute('SELECT customer_id FROM orders WHERE order_id=?', (order_id,)).fetchone()
            if owner and owner[0] == customer_id:
                return {'order_id': order_id, 'status': 'cancelled', 'already_cancelled': True}
        order = order_row(conn, order_id, customer_id)
        if is_placed(conn, order):
            raise BillingError('Issued invoices are immutable; use a credit note for adjustments.')
        if action == 'cancel':
            reason = text(reason, 'Cancellation reason')
            currency = conn.execute("SELECT value FROM billing_config WHERE key='currency'").fetchone()[0]
            conn.execute("INSERT INTO order_details(order_id,currency,status,cancellation_reason) VALUES (?,?,'cancelled',?) "
                         "ON CONFLICT(order_id) DO UPDATE SET status='cancelled',cancellation_reason=excluded.cancellation_reason",
                         (order_id, currency, reason))
            return {'order_id': order_id, 'status': 'cancelled', 'reason': reason}
        if action != 'replace_items' or not isinstance(items, list) or not 1 <= len(items) <= 100:
            raise BillingError('Use cancel or replace_items with 1-100 line items.')
        quantities = {}
        for line in items:
            if not isinstance(line, dict):
                raise BillingError('Each item must contain item_code and quantity.')
            code = identifier(line.get('item_code'), 'item code')
            qty = line.get('quantity')
            if type(qty) is not int or not 1 <= qty <= 100000:
                raise BillingError('Quantity must be an integer from 1 to 100000.')
            quantities[code] = quantities.get(code, 0) + qty
            if quantities[code] > 100000:
                raise BillingError('Combined quantity exceeds 100000.')
        subtotal = Decimal(0)
        for code, qty in quantities.items():
            item = conn.execute('SELECT * FROM items WHERE item_code=?', (code,)).fetchone()
            if not item or item['availablequantity'] < qty:
                raise BillingError(f'Item {code} is unavailable or has insufficient stock.')
            subtotal += price_for(conn, item, order['order_date']) * qty
        values = totals(conn, subtotal, order['promo_code'])
        conn.execute('DELETE FROM order_requests WHERE order_id=?', (order_id,))
        conn.executemany('INSERT INTO order_requests(order_id,item_code,quantity) VALUES (?,?,?)',
                         [(order_id, code, qty) for code, qty in quantities.items()])
        update_totals(conn, order_id, values)
        return {'order_id': order_id, 'status': 'requested', 'estimate': values}


@tool_result
def set_invoice_due_date(order_id: str, customer_id: str, due_date: str, reason: str,
                         confirmed: bool = False) -> dict:
    """Set or extend a placed invoice's due date after explicit confirmation. Does not alter invoice amounts."""
    confirm(confirmed)
    due = iso_date(due_date)
    reason = text(reason, 'Reason')
    with transaction() as conn:
        row = account(conn, order_id, customer_id)
        order_date = conn.execute('SELECT order_date FROM orders WHERE order_id=?', (order_id,)).fetchone()[0]
        if due < iso_date(order_date):
            raise BillingError('Due date cannot be before the order date.')
        conn.execute('INSERT INTO order_details(order_id,currency,due_date) VALUES (?,?,?) '
                     'ON CONFLICT(order_id) DO UPDATE SET due_date=excluded.due_date', (order_id, row['currency'], due_date))
        return {'order_id': order_id, 'due_date': due_date, 'reason': reason}


@tool_result
def manage_payment(action: str, order_id: str, customer_id: str, payment_id: str,
                   amount: str | None = None, currency: str | None = None,
                   reference: str = '', method: str = 'bank_transfer', received_date: str | None = None,
                   reason: str = '', confirmed: bool = False) -> dict:
    """Record a received payment or reverse an erroneous receipt, after explicit confirmation.

    action: record or reverse. Require operator-provided payment_id and unique external reference for record.
    Receipt must be positive, match invoice currency and not exceed amount_due. Never charges a bank/card.
    A reversal corrects a ledger receipt, not a customer refund. Reuse payment_id for identical retries.
    """
    confirm(confirmed)
    identifier(payment_id, 'payment ID')
    with transaction() as conn:
        row = account(conn, order_id, customer_id)
        prior = conn.execute('SELECT * FROM payments WHERE payment_id=?', (payment_id,)).fetchone()
        if action == 'reverse':
            reason = text(reason, 'Reversal reason')
            if not prior or prior['order_id'] != order_id:
                raise BillingError('Payment not found for this invoice.')
            if prior['reversed']:
                if prior['reversal_reason'] != reason:
                    raise BillingError('Payment was already reversed with a different reason.')
                return {'payment_id': payment_id, 'already_reversed': True, 'account': row}
            conn.execute('UPDATE payments SET reversed=1,reversal_reason=? WHERE payment_id=?', (reason, payment_id))
        elif action == 'record':
            value = cents(amount)
            reference = text(reference, 'External payment reference', 200)
            if method not in ('bank_transfer', 'cash', 'card', 'check', 'other'):
                raise BillingError('Use bank_transfer, cash, card, check or other as the method.')
            received = iso_date(received_date) if received_date else date.today()
            if received > date.today():
                raise BillingError('A received payment cannot have a future date.')
            if value <= 0 or currency != row['currency']:
                raise BillingError('Payment must be positive and use the invoice currency exactly.')
            expected = (order_id, value, currency, reference, method, received.isoformat())
            if prior:
                actual = tuple(prior[k] for k in ('order_id','amount_cents','currency','reference','method','received_date'))
                if actual != expected:
                    raise BillingError('Payment ID already used with different receipt details.')
                return {'payment_id': payment_id, 'already_recorded': True, 'reversed': bool(prior['reversed']), 'account': row}
            if value > cents(row['amount_due']):
                raise BillingError('Payment exceeds the outstanding local invoice balance. Review existing receipts and adjustments.')
            if conn.execute('SELECT 1 FROM payments WHERE reference=?', (reference,)).fetchone():
                raise BillingError('This external payment reference has already been recorded.')
            conn.execute('INSERT INTO payments(payment_id,order_id,amount_cents,currency,reference,method,received_date) '
                         'VALUES (?,?,?,?,?,?,?)', (payment_id, *expected))
        else:
            raise BillingError('Action must be record or reverse.')
        return {'payment_id': payment_id, 'action': action, 'account': account(conn, order_id, customer_id), 'note': LEDGER_NOTE}


@tool_result
def issue_credit_note(order_id: str, customer_id: str, credit_id: str, amount: str,
                      reason: str, confirmed: bool = False) -> dict:
    """Issue an immutable monetary credit against a placed invoice after confirmation.

    Credits and existing ledger refunds together cannot exceed the invoice total. No stock or cash movement.
    Use a stable credit_id for safe retries. Does not modify original invoice lines or tax calculation.
    """
    confirm(confirmed)
    identifier(credit_id, 'credit ID')
    value, reason = cents(amount), text(reason, 'Credit reason')
    with transaction() as conn:
        row = account(conn, order_id, customer_id)
        prior = conn.execute('SELECT * FROM credit_notes WHERE credit_id=?', (credit_id,)).fetchone()
        if prior:
            if (prior['order_id'],prior['amount_cents'],prior['reason']) != (order_id,value,reason):
                raise BillingError('Credit ID is already used with different details.')
            return {'credit_id': credit_id, 'already_issued': True, 'account': row}
        if value <= 0 or value > cents(row['adjusted_total']):
            raise BillingError('Credit must be positive and cannot exceed the invoice less existing credits and refunds.')
        conn.execute('INSERT INTO credit_notes(credit_id,order_id,amount_cents,currency,reason) VALUES (?,?,?,?,?)',
                     (credit_id,order_id,value,row['currency'],reason))
        return {'credit_id': credit_id, 'account': account(conn, order_id, customer_id), 'note': LEDGER_NOTE}


@tool_result
def billing_statement(customer_id: str | None = None, order_id: str | None = None,
                      aging_date: str | None = None, limit: int = 25, offset: int = 0) -> dict:
    """Customer statements, invoice balances, payment reconciliation and company receivables aging.

    Totals include ALL matched invoices, grouped by currency. Only invoice details are paginated.
    aging_date changes aging buckets, not the accounting cutoff. Unknown legacy due dates stay unknown.
    For one order includes receipt, credit and dispute details. No database writes.
    """
    if type(limit) is not int or not 1 <= limit <= 100 or type(offset) is not int or offset < 0:
        raise BillingError('Limit must be 1-100 and offset must be nonnegative.')
    with reading() as conn:
        if customer_id:
            ensure_customer(conn, customer_id)
        rows = accounts(conn, customer_id, order_id, aging_date)
        if order_id and not rows:
            raise BillingError('Placed invoice not found for the selected customer.')
        grouped = {}
        fields = ('charged', 'credits', 'ledger_refunds', 'recorded_payments', 'amount_due', 'customer_credit')
        for row in rows:
            group = grouped.setdefault(row['currency'], {**{k: 0 for k in fields}, 'aging': {}, 'invoice_count': 0})
            group['invoice_count'] += 1
            for k in fields:
                group[k] += cents(row[k])
            bucket = row['aging_bucket']
            group['aging'][bucket] = group['aging'].get(bucket, 0) + cents(row['amount_due'])
        for group in grouped.values():
            for k in fields:
                group[k] = cash(group[k])
            group['aging'] = {k: cash(v) for k,v in group['aging'].items()}
        result = {'matched_invoices': len(rows), 'totals_by_currency': grouped,
                  'invoices': rows[offset:offset+limit], 'offset': offset,
                  'next_offset': offset+limit if offset+limit < len(rows) else None, 'note': LEDGER_NOTE}
        if order_id:
            for table in ('payments','credit_notes','billing_disputes'):
                result[table] = [dict(r) for r in conn.execute(f'SELECT * FROM {table} WHERE order_id=? ORDER BY created_at LIMIT 101', (order_id,))]
                result[table+'_truncated'] = len(result[table]) > 100
                result[table] = result[table][:100]
        return result


@tool_result
def manage_dispute(action: str, order_id: str, customer_id: str, dispute_id: str,
                   reason: str, confirmed: bool = False) -> dict:
    """Open or resolve a billing dispute after confirmation. Opening suppresses reminder drafts.

    reason is the complaint when opening and the resolution when resolving. No automatic credit/refund.
    """
    confirm(confirmed)
    identifier(dispute_id, 'dispute ID')
    reason = text(reason, 'Reason or resolution')
    with transaction() as conn:
        account(conn, order_id, customer_id)
        existing = conn.execute('SELECT * FROM billing_disputes WHERE dispute_id=?', (dispute_id,)).fetchone()
        if action == 'open':
            if existing:
                if existing['order_id'] != order_id or existing['reason'] != reason:
                    raise BillingError('Dispute ID already exists with different details.')
                return dict(existing)
            if conn.execute("SELECT 1 FROM billing_disputes WHERE order_id=? AND status='open'", (order_id,)).fetchone():
                raise BillingError('An open dispute already exists for this invoice.')
            conn.execute("INSERT INTO billing_disputes(dispute_id,order_id,reason,status) VALUES (?,?,?,'open')", (dispute_id,order_id,reason))
        elif action == 'resolve':
            if not existing or existing['order_id'] != order_id:
                raise BillingError('Dispute not found for this invoice.')
            if existing['status'] == 'resolved':
                if existing['resolution'] != reason:
                    raise BillingError('Dispute is already resolved with a different resolution.')
                return dict(existing)
            conn.execute("UPDATE billing_disputes SET status='resolved',resolution=?,resolved_at=CURRENT_TIMESTAMP WHERE dispute_id=?", (reason,dispute_id))
        else:
            raise BillingError('Action must be open or resolve.')
        return dict(conn.execute('SELECT * FROM billing_disputes WHERE dispute_id=?', (dispute_id,)).fetchone())


@tool_result
def prepare_payment_reminder(order_id: str, customer_id: str) -> dict:
    """Draft an overdue payment reminder for review; NEVER sends email. Rejects settled/disputed/undated invoices."""
    with reading() as conn:
        row = account(conn, order_id, customer_id)
        if row['disputed']:
            raise BillingError('An open dispute suppresses payment reminders. Resolve it first.')
        if not row['days_overdue'] or cents(row['amount_due']) == 0:
            raise BillingError('No overdue balance with a known due date exists for this invoice.')
        if not row['email']:
            raise BillingError('Customer email is missing. Update the customer record first.')
        return {'status': 'draft_only', 'sent': False, 'to': row['email'],
            'subject': f"Payment reminder for invoice {row['invoice_number']}",
            'body': f"Hello {row['customer_name']},\n\nOur local records show an outstanding balance of "
                    f"{row['currency']} {row['amount_due']} for invoice {row['invoice_number']}, "
                    f"due {row['due_date']}. If you have already paid, please share the payment reference "
                    'so we can reconcile our records. Please contact us if you have a billing question.\n\nThank you.',
            'note': 'Review balances and contact details before sending through your own email service. ' + LEDGER_NOTE}
