"""Exact minor-unit reconciliation for locally recorded receivables."""
from datetime import date
from decimal import Decimal
from mcp_server.tools.billing_tools import BillingError, money


def cents(value):
    return int(money(value) * 100)


def cash(value):
    return format(Decimal(value) / 100, '.2f')


def iso_date(value):
    try:
        parsed = date.fromisoformat(value)
        if parsed.isoformat() != value:
            raise ValueError()
        return parsed
    except (TypeError, ValueError):
        raise BillingError('Use a valid date in YYYY-MM-DD format.') from None


def accounts(conn, customer_id=None, order_id=None, aging_date=None):
    today = iso_date(aging_date) if aging_date else date.today()
    clauses, args = ['o.order_invoice IS NOT NULL'], []
    for field, value in [('customer_id', customer_id), ('order_id', order_id)]:
        if value is not None:
            clauses.append('o.' + field + '=?')
            args.append(value)
    rows = conn.execute('''SELECT o.*, c.name AS customer_name, c.email,
        d.due_date, d.currency AS invoice_currency, d.customer_snapshot,
        (SELECT COALESCE(SUM(p.amount_cents),0) FROM payments p
            WHERE p.order_id=o.order_id AND p.reversed=0) AS paid_cents,
        (SELECT COALESCE(SUM(cn.amount_cents),0) FROM credit_notes cn
            WHERE cn.order_id=o.order_id) AS credit_cents,
        EXISTS(SELECT 1 FROM billing_disputes b WHERE b.order_id=o.order_id AND b.status='open') AS disputed
        FROM orders o JOIN customers c ON c.customer_id=o.customer_id
        LEFT JOIN order_details d ON d.order_id=o.order_id WHERE ''' + ' AND '.join(clauses) +
        ' ORDER BY d.due_date IS NULL,d.due_date,o.order_id', args).fetchall()
    configured = conn.execute("SELECT value FROM billing_config WHERE key='currency'").fetchone()
    currency = configured[0] if configured else 'USD'
    result = []
    for row in rows:
        charged, refunded = cents(row['charged_price']), cents(row['refund_amount'] or 0)
        adjusted = charged - refunded - row['credit_cents']
        balance = adjusted - row['paid_cents']
        overdue = max(0, (today - iso_date(row['due_date'])).days) if row['due_date'] else None
        bucket = ('unknown_due_date' if overdue is None else 'current' if overdue == 0
                  else '1_30' if overdue <= 30 else '31_60' if overdue <= 60
                  else '61_90' if overdue <= 90 else 'over_90')
        result.append({'order_id': row['order_id'], 'invoice_number': row['order_invoice'],
            'customer_id': row['customer_id'], 'customer_name': row['customer_name'], 'email': row['email'],
            'currency': row['invoice_currency'] or currency,
            'currency_inferred': row['invoice_currency'] is None,
            'due_date': row['due_date'], 'days_overdue': overdue, 'aging_bucket': bucket,
            'charged': cash(charged), 'credits': cash(row['credit_cents']), 'ledger_refunds': cash(refunded),
            'recorded_payments': cash(row['paid_cents']), 'adjusted_total': cash(adjusted),
            'amount_due': cash(max(0, balance)), 'customer_credit': cash(max(0, -balance)),
            'status': 'customer_credit' if balance < 0 else 'settled' if balance == 0
                      else 'partial' if row['paid_cents'] else 'unpaid_in_local_ledger',
            'disputed': bool(row['disputed']),
            'legacy_invoice': row['customer_snapshot'] is None})
    return result


def account(conn, order_id, customer_id):
    rows = accounts(conn, customer_id=customer_id, order_id=order_id)
    if not rows:
        raise BillingError('Placed invoice not found for this customer.')
    return rows[0]


LEDGER_NOTE = ('Balances use local recorded receipts, credit notes and ledger refunds only. '
    'They do not verify bank settlement. Legacy invoices may lack imported payment history and due dates. '
    'Customer credit is a liability to review, not proof that money was returned. '
    'Aging date changes age buckets only; this is not a historical balance reconstruction.')
