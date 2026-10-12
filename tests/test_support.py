from concurrent.futures import ThreadPoolExecutor
import sqlite3
import pytest

from database.connection import connect
from mcp_server.tools.billing_tools import request_order, place_order
from mcp_server.tools.operations_tools import billing_statement
from mcp_server.tools.support_tools import manage_billing_case, get_billing_cases


def create(case_id='CASE1', event_id='EVENT1', **kwargs):
    return manage_billing_case('create',case_id,'CUST001',event_id,'Customer says payment was made',
                               category='payment',confirmed=True,**kwargs)


def change(status,version,event='EVENT2',source='operator_verified',note='Staff reviewed the available evidence'):
    return manage_billing_case('change_status','CASE1','CUST001',event,note,
        status=status,expected_version=version,source=source,confirmed=True)


def test_claim_tracking_does_not_record_receipt():
    oid = request_order('CUST001',[{'item_code':'ITEM001','quantity':1}],'ORDER1')['order_id']
    place_order(oid,'CUST001')
    assert create(order_id=oid)['ok']
    result = get_billing_cases('CUST001','CASE1')
    assert result['events'][0]['source'] == 'customer_reported'
    assert result['case']['status'] == 'open'
    assert billing_statement(order_id=oid)['invoices'][0]['recorded_payments'] == '0.00'
    assert change('resolved',1)['ok']
    assert billing_statement(order_id=oid)['invoices'][0]['recorded_payments'] == '0.00'


def test_duplicate_events_are_idempotent_and_conflicts_rejected():
    assert create()['ok']
    assert create()['already_recorded']
    assert not manage_billing_case('create','CASE1','CUST001','EVENT1','Different note',confirmed=True)['ok']
    assert not create(case_id='CASE2')['ok']
    assert get_billing_cases('CUST001')['matched_cases'] == 1
    assert len(get_billing_cases('CUST001','CASE1')['events']) == 1


def test_case_owner_and_linked_order_checked():
    oid = request_order('CUST002',[{'item_code':'ITEM001','quantity':1}])['order_id']
    assert not create(order_id=oid)['ok']
    assert create()['ok']
    assert not get_billing_cases('CUST002','CASE1')['ok']
    assert not manage_billing_case('add_note','CASE1','CUST002','E2','A note',expected_version=1,confirmed=True)['ok']


def test_confirmation_required():
    assert not manage_billing_case('create','CASE1','CUST001','EVENT1','Problem')['ok']
    assert get_billing_cases('CUST001')['matched_cases'] == 0


def test_status_resolution_and_reopening_preserve_events():
    create()
    assert not change('closed',1)['ok']
    assert not change('resolved',1,source='customer_reported')['ok']
    assert change('escalated',1)['case']['version'] == 2
    assert change('resolved',2,'EVENT3')['case']['resolution']
    assert change('closed',3,'EVENT4')['ok']
    assert not manage_billing_case('add_note','CASE1','CUST001','EVENT5','Late note',expected_version=4,confirmed=True)['ok']
    assert change('open',4,'EVENT5',note='Customer supplied new evidence')['case']['resolution'] is None
    events = get_billing_cases('CUST001','CASE1')['events']
    assert len(events) == 5 and events[2]['resulting_status'] == 'resolved'


def test_stale_update_rejected_but_identical_retry_allowed():
    create()
    assert change('under_review',1)['ok']
    assert change('under_review',1)['already_recorded']
    assert not change('escalated',1,'EVENT3')['ok']
    assert get_billing_cases('CUST001','CASE1')['case']['version'] == 2


def test_concurrent_updates_do_not_overwrite_each_other():
    create()
    with ThreadPoolExecutor(2) as pool:
        futures = [pool.submit(change,status,1,event) for status,event in [('under_review','E2'),('escalated','E3')]]
        results = [future.result() for future in futures]
    assert sum(r['ok'] for r in results) == 1
    assert get_billing_cases('CUST001','CASE1')['case']['version'] == 2


def test_pagination_and_status_filters():
    create()
    create('CASE2','EVENT2')
    assert get_billing_cases('CUST001',limit=1)['next_offset'] == 1
    assert len(get_billing_cases('CUST001',limit=1,offset=1)['cases']) == 1
    assert change('awaiting_customer',1,'E3')['ok']
    assert get_billing_cases('CUST001',status='awaiting_customer')['matched_cases'] == 1
    assert get_billing_cases('CUST001','CASE1',limit=1)['next_offset'] == 1
    assert get_billing_cases('CUST001','CASE1',limit=1,offset=1)['next_offset'] is None


@pytest.mark.parametrize('category',['unknown','',"payment'); DROP TABLE customers;--"])
def test_bad_categories_rejected(category):
    assert not manage_billing_case('create','C1','CUST001','E1','Problem',category=category,confirmed=True)['ok']
    assert get_billing_cases('CUST001')['matched_cases'] == 0


def test_case_history_append_only_and_audited():
    create()
    conn = connect()
    try:
        assert conn.execute("SELECT COUNT(*) FROM billing_audit WHERE action='manage_billing_case'").fetchone()[0] == 1
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("UPDATE billing_case_events SET note='Replacement'")
        conn.rollback()
        assert get_billing_cases('CUST001','CASE1')['events'][0]['note'] == 'Customer says payment was made'
    finally:
        conn.close()
