from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
import json
import sqlite3
import pytest

from database.connection import transaction, connect, initialize
from mcp_server.tools.billing_tools import request_order, place_order, process_refund, apply_promotion
from mcp_server.tools.operations_tools import (manage_customer, manage_draft, set_invoice_due_date,
    manage_payment, issue_credit_note, billing_statement, manage_dispute, prepare_payment_reminder)
from mcp_server.tools.analytics_tools import billing_analysis, billing_anomalies


def invoice(oid='ORDER1'):
    assert request_order('CUST001', [{'item_code':'ITEM001','quantity':2}], oid)['ok']
    result = place_order(oid, 'CUST001')
    assert result['ok'], result
    return oid


def receipt(oid='ORDER1', pid='PAY1', amount='50.00', reference='BANK1', **kwargs):
    return manage_payment('record', oid, 'CUST001', pid, amount=amount, currency='USD',
                          reference=reference, received_date=date.today().isoformat(), confirmed=True, **kwargs)


def current(oid='ORDER1'):
    return billing_statement(order_id=oid)['invoices'][0]


def test_receipt_credit_reversal_and_retries():
    oid = invoice()
    assert current()['amount_due'] == '159.80'
    assert receipt()['account']['amount_due'] == '109.80'
    assert receipt()['already_recorded']
    assert not receipt(amount='60')['ok']
    assert not receipt(pid='PAY2')['ok']  # Duplicate external reference.
    credit = issue_credit_note(oid, 'CUST001', 'CN1', '20', 'Service adjustment', True)
    assert credit['account']['amount_due'] == '89.80'
    assert issue_credit_note(oid, 'CUST001', 'CN1', '20', 'Service adjustment', True)['already_issued']
    assert not issue_credit_note(oid, 'CUST001', 'CN1', '21', 'Service adjustment', True)['ok']
    assert manage_payment('reverse', oid, 'CUST001', 'PAY1', reason='Wrong bank reference', confirmed=True)['ok']
    assert current()['amount_due'] == '139.80'
    assert manage_payment('reverse', oid, 'CUST001', 'PAY1', reason='Wrong bank reference', confirmed=True)['already_reversed']
    assert receipt()['reversed']
    assert current()['amount_due'] == '139.80'


@pytest.mark.parametrize('amount', ['0','-1','NaN','Infinity','99999999999','160'])
def test_invalid_or_excess_payments(amount):
    invoice()
    assert not receipt(amount=amount)['ok']
    assert current()['recorded_payments'] == '0.00'


def test_confirmation_and_ownership():
    oid = invoice()
    assert not manage_payment('record',oid,'CUST001','PAY1',amount='10',currency='USD',reference='B')['ok']
    assert not issue_credit_note(oid,'CUST001','C1','10','adjustment')['ok']
    assert not issue_credit_note(oid,'CUST002','C1','10','adjustment',True)['ok']
    assert not manage_payment('record',oid,'CUST002','PAY1',amount='10',currency='USD',reference='B',confirmed=True)['ok']
    assert not manage_payment('record',oid,'CUST001','PAY1',amount='10',currency='EUR',reference='B',confirmed=True)['ok']
    assert current()['amount_due'] == '159.80'


def test_concurrent_receipts_cannot_overpay():
    invoice()
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(lambda n: receipt(pid='P'+str(n),reference='B'+str(n),amount='100'), (1,2)))
    assert sum(r['ok'] for r in results) == 1
    assert current()['amount_due'] == '59.80'


def test_credits_and_refunds_share_remaining_limit():
    oid = invoice()
    assert issue_credit_note(oid,'CUST001','C1','100','adjustment',True)['ok']
    assert not process_refund(oid,'CUST001','Return','60')['ok']
    assert process_refund(oid,'CUST001','Return')['refund_amount'] == '59.80'
    assert not issue_credit_note(oid,'CUST001','C2','0.01','extra',True)['ok']
    assert current()['amount_due'] == '0.00'


def test_paid_invoice_credit_creates_customer_liability():
    oid = invoice()
    assert receipt(amount='159.80')['ok']
    assert issue_credit_note(oid,'CUST001','C1','10','adjustment',True)['ok']
    row = current()
    assert row['amount_due'] == '0.00' and row['customer_credit'] == '10.00'
    assert row['status'] == 'customer_credit'


def test_cancel_and_replace_drafts_keep_stock_and_history():
    oid = request_order('CUST001',[{'item_code':'ITEM001','quantity':1}],'DRAFT')['order_id']
    before = billing_analysis()['draft_count']
    result = manage_draft(oid,'CUST001','replace_items',[{'item_code':'ITEM002','quantity':3}],confirmed=True)
    assert result['estimate']['charged_price'] == '88.50'
    assert not manage_draft(oid,'CUST001','replace_items',[{'item_code':'ITEM002','quantity':999}],confirmed=True)['ok']
    assert manage_draft(oid,'CUST001','cancel',reason='Duplicate request',confirmed=True)['ok']
    assert manage_draft(oid,'CUST001','cancel',reason='Duplicate request',confirmed=True)['already_cancelled']
    assert not place_order(oid,'CUST001')['ok']
    assert not apply_promotion(oid,'CUST001','SAVE10')['ok']
    assert not request_order('CUST001',[{'item_code':'ITEM002','quantity':3}],oid)['ok']
    assert billing_analysis()['draft_count'] == before-1
    assert billing_anomalies()['finding_count'] == 0
    conn = connect()
    try:
        assert conn.execute("SELECT availablequantity FROM items WHERE item_code='ITEM002'").fetchone()[0] == 60
        assert conn.execute('SELECT COUNT(*) FROM orders').fetchone()[0] == 1
        assert conn.execute('SELECT quantity FROM order_requests WHERE order_id=?',(oid,)).fetchone()[0] == 3
    finally:
        conn.close()


def test_due_dates_aging_disputes_and_reminders():
    oid = invoice()
    yesterday = (date.today()-timedelta(days=1)).isoformat()
    with transaction() as conn:
        conn.execute("UPDATE orders SET order_date='2020-01-01' WHERE order_id=?",(oid,))
    assert set_invoice_due_date(oid,'CUST001',yesterday,'Agreed terms',True)['ok']
    assert current()['aging_bucket'] == '1_30'
    reminder = prepare_payment_reminder(oid,'CUST001')
    assert reminder['ok'] and reminder['sent'] is False and '159.80' in reminder['body']
    assert manage_dispute('open',oid,'CUST001','DIS1','Wrong item',True)['ok']
    assert not prepare_payment_reminder(oid,'CUST001')['ok']
    assert not manage_dispute('resolve',oid,'CUST002','DIS1','Resolved',True)['ok']
    assert manage_dispute('resolve',oid,'CUST001','DIS1','Amount accepted',True)['ok']
    assert prepare_payment_reminder(oid,'CUST001')['ok']
    assert receipt(amount='159.80')['ok']
    assert not prepare_payment_reminder(oid,'CUST001')['ok']


def test_snapshots_and_currency_grouping():
    invoice()
    assert manage_customer('CUST001','Changed name','New company','new@example.com','update',True)['ok']
    with transaction() as conn:
        meta = conn.execute("SELECT * FROM order_details WHERE order_id='ORDER1'").fetchone()
        assert json.loads(meta['customer_snapshot'])['name'] == 'Alex Morgan'
        conn.execute("UPDATE billing_config SET value='EUR' WHERE key='currency'")
    invoice('ORDER2')
    result = billing_statement(customer_id='CUST001',limit=1)
    assert result['matched_invoices'] == 2 and result['next_offset'] == 1
    assert result['totals_by_currency']['USD']['charged'] == '159.80'
    assert result['totals_by_currency']['EUR']['charged'] == '159.80'
    assert current()['currency'] == 'USD'
    assert not billing_analysis()['ok']
    assert billing_analysis(order_id='ORDER1')['currency'] == 'USD'


def test_legacy_migration_idempotent_and_unknown_terms():
    oid = invoice()
    with transaction() as conn:
        conn.execute('DELETE FROM order_details WHERE order_id=?',(oid,))
    initialize()
    initialize()
    row = current()
    assert row['legacy_invoice'] and row['currency_inferred']
    assert row['aging_bucket'] == 'unknown_due_date'
    assert not prepare_payment_reminder(oid,'CUST001')['ok']


def test_audit_success_only_and_append_only():
    invoice()
    conn = connect()
    try:
        count = conn.execute('SELECT COUNT(*) FROM billing_audit').fetchone()[0]
        assert count == 2
        assert not receipt(amount='1000')['ok']
        assert conn.execute('SELECT COUNT(*) FROM billing_audit').fetchone()[0] == count
        assert receipt()['ok']
        assert conn.execute('SELECT COUNT(*) FROM billing_audit').fetchone()[0] == count+1
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute('DELETE FROM billing_audit')
        conn.rollback()
    finally:
        conn.close()


def test_changed_quote_requires_reconfirmation_and_rolls_back_inventory():
    oid = request_order('CUST001',[{'item_code':'ITEM001','quantity':2}],'QUOTE')['order_id']
    with transaction() as conn:
        conn.execute("UPDATE billing_config SET value='5' WHERE key='shipping_amount'")
    assert not place_order(oid,'CUST001')['ok']
    conn = connect()
    try:
        assert conn.execute('SELECT COUNT(*) FROM invoice_lines').fetchone()[0] == 0
        assert conn.execute("SELECT availablequantity FROM items WHERE item_code='ITEM001'").fetchone()[0] == 40
    finally:
        conn.close()
    refreshed = manage_draft(oid,'CUST001','replace_items',[{'item_code':'ITEM001','quantity':2}],confirmed=True)
    assert refreshed['estimate']['charged_price'] == '164.80'
    assert place_order(oid,'CUST001')['charged_price'] == '164.80'


def test_changed_draft_currency_requires_new_draft():
    oid = request_order('CUST001',[{'item_code':'ITEM001','quantity':1}],'QUOTE')['order_id']
    with transaction() as conn:
        conn.execute("UPDATE billing_config SET value='EUR' WHERE key='currency'")
    assert not place_order(oid,'CUST001')['ok']


def test_concurrent_credit_and_refund_cannot_exceed_invoice():
    oid = invoice()
    with ThreadPoolExecutor(2) as pool:
        one = pool.submit(issue_credit_note,oid,'CUST001','CN1','100','Adjustment',True)
        two = pool.submit(process_refund,oid,'CUST001','Return','100')
        results = [one.result(),two.result()]
    assert sum(r['ok'] for r in results) == 1
    assert current()['amount_due'] == '59.80'


def test_customer_creation_validation_and_idempotency():
    assert not manage_customer('NEW','New Customer',confirmed=False)['ok']
    assert not manage_customer('NEW','New Customer',email='bad-email',confirmed=True)['ok']
    assert manage_customer('NEW','New Customer',email='new@example.com',confirmed=True)['ok']
    assert manage_customer('NEW','New Customer',email='new@example.com',confirmed=True)['already_exists']
    assert not manage_customer('NEW','Different',confirmed=True)['ok']


def test_future_receipt_and_bad_due_date_rejected():
    oid = invoice()
    assert not manage_payment('record',oid,'CUST001','P1',amount='10',currency='USD',reference='B1',
        received_date=(date.today()+timedelta(days=1)).isoformat(),confirmed=True)['ok']
    assert not set_invoice_due_date(oid,'CUST001','bad-date','terms',True)['ok']
    assert not set_invoice_due_date(oid,'CUST001','2000-01-01','terms',True)['ok']
