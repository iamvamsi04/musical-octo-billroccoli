"""Persistent support cases for staff assisting customers; no outbound notifications."""
from database.connection import transaction
from mcp_server.tools.billing_tools import BillingError, tool_result, identifier
from mcp_server.tools.operations_tools import confirm, text, reading, ensure_customer

CATEGORIES = {'invoice','payment','refund','dispute','order','account','other'}
TRANSITIONS = {
    'open': {'awaiting_customer','under_review','escalated','resolved'},
    'awaiting_customer': {'open','under_review','escalated','resolved'},
    'under_review': {'open','awaiting_customer','escalated','resolved'},
    'escalated': {'open','awaiting_customer','under_review','resolved'},
    'resolved': {'open','closed'},
    'closed': {'open'},
}
NOTE = ('This is a local support record. Escalation marks it for staff review; no human or email '
        'service has been notified. A case update does not record payment, refund money, issue credit, '
        'resolve a financial dispute or change an order.')


@tool_result
def manage_billing_case(action: str, case_id: str, customer_id: str, event_id: str,
                        note: str, source: str = 'customer_reported', category: str = 'other',
                        order_id: str | None = None, priority: str = 'normal',
                        status: str | None = None, expected_version: int | None = None,
                        confirmed: bool = False) -> dict:
    """Create a billing support case, add_note, or change_status after operator approval.

    Create: note is the problem summary; use a stable case_id and event_id. Order is optional.
    Updates require expected_version from get_billing_cases. Reuse event_id for identical retries.
    Source customer_reported records a claim, not verified payment. operator_verified requires staff evidence.
    Statuses: open, awaiting_customer, under_review, escalated, resolved, closed. Resolve needs a
    meaningful resolution note and operator_verified source. Only resolved cases may close; reopen to open.
    Escalation does not send a notification. A support case does not suspend reminders; use manage_dispute.
    """
    confirm(confirmed)
    identifier(case_id,'case ID')
    identifier(event_id,'event ID')
    identifier(customer_id,'customer ID')
    note = text(note,'Case note',2000)
    if source not in ('customer_reported','operator_verified'):
        raise BillingError('Source must be customer_reported or operator_verified.')
    if action not in ('create','add_note','change_status'):
        raise BillingError('Action must be create, add_note or change_status.')
    with transaction() as conn:
        ensure_customer(conn,customer_id)
        row = conn.execute('SELECT * FROM billing_cases WHERE case_id=?',(case_id,)).fetchone()
        if row and row['customer_id'] != customer_id:
            raise BillingError('Case not found for this customer.')
        prior = conn.execute('SELECT * FROM billing_case_events WHERE event_id=?',(event_id,)).fetchone()
        if prior:
            if not row or (prior['case_id'],prior['action'],prior['note'],prior['source']) != (case_id,action,note,source):
                raise BillingError('Event ID already used for different case details.')
            if action == 'change_status' and prior['resulting_status'] != status:
                raise BillingError('Event ID already used for a different status transition.')
            if action == 'create' and (row['order_id'],row['category'],row['priority']) != (order_id,category,priority):
                raise BillingError('Event ID already used for different case details.')
            return {'case':dict(row),'already_recorded':True,'note':NOTE}
        if action == 'create':
            if row:
                raise BillingError('Case ID already exists. Retrieve it before updating.')
            if category not in CATEGORIES or priority not in ('normal','urgent') or status not in (None,'open'):
                raise BillingError('Choose a valid category/priority. New cases start open.')
            if order_id is not None and not conn.execute('SELECT 1 FROM orders WHERE order_id=? AND customer_id=?',
                                                        (order_id,customer_id)).fetchone():
                raise BillingError('Order not found for this customer.')
            conn.execute('INSERT INTO billing_cases(case_id,customer_id,order_id,category,summary,priority) VALUES (?,?,?,?,?,?)',
                         (case_id,customer_id,order_id,category,note,priority))
            resulting_status = 'open'
        else:
            if not row:
                raise BillingError('Case not found for this customer.')
            if type(expected_version) is not int or expected_version != row['version']:
                raise BillingError('Case changed or version is missing. Retrieve the latest case and review before retrying.')
            if action == 'add_note':
                if status is not None:
                    raise BillingError('Use change_status to change a case status.')
                if row['status'] == 'closed':
                    raise BillingError('Reopen the closed case before adding a note.')
                resulting_status = row['status']
            else:
                if status not in TRANSITIONS[row['status']]:
                    raise BillingError('Invalid status transition. Resolve before closing; closed cases must first reopen.')
                if status in ('resolved','closed') and source != 'operator_verified':
                    raise BillingError('Staff must verify the outcome before resolving or closing a case.')
                resulting_status = status
            resolution = note if resulting_status == 'resolved' and action == 'change_status' else row['resolution']
            if resulting_status == 'open' and action == 'change_status':
                resolution = None
            conn.execute('UPDATE billing_cases SET status=?,resolution=?,version=version+1,updated_at=CURRENT_TIMESTAMP WHERE case_id=?',
                         (resulting_status,resolution,case_id))
        conn.execute('INSERT INTO billing_case_events(event_id,case_id,action,note,source,resulting_status) VALUES (?,?,?,?,?,?)',
                     (event_id,case_id,action,note,source,resulting_status))
        updated = dict(conn.execute('SELECT * FROM billing_cases WHERE case_id=?',(case_id,)).fetchone())
        return {'case':updated,'note':NOTE}


@tool_result
def get_billing_cases(customer_id: str, case_id: str | None = None, status: str | None = None,
                      limit: int = 20, offset: int = 0) -> dict:
    """Read support case status and follow-up history for one customer. Paginate case lists or a case's events.

    With case_id, limit/offset page its event timeline. Without case_id, they page cases.
    Use returned version when updating. Source labels separate customer claims from staff-verified notes.
    """
    if type(limit) is not int or not 1 <= limit <= 100 or type(offset) is not int or offset < 0:
        raise BillingError('Limit must be 1-100; offset must be nonnegative.')
    if status is not None and status not in TRANSITIONS:
        raise BillingError('Unknown case status.')
    with reading() as conn:
        ensure_customer(conn,customer_id)
        if case_id:
            row = conn.execute('SELECT * FROM billing_cases WHERE case_id=? AND customer_id=?',(case_id,customer_id)).fetchone()
            if not row:
                raise BillingError('Case not found for this customer.')
            events = [dict(r) for r in conn.execute('SELECT * FROM billing_case_events WHERE case_id=? ORDER BY rowid LIMIT ? OFFSET ?',
                                                   (case_id,limit+1,offset))]
            return {'case':dict(row),'events':events[:limit],
                    'next_offset':offset+limit if len(events)>limit else None,'note':NOTE}
        where,args = 'customer_id=?',[customer_id]
        if status:
            where += ' AND status=?'
            args.append(status)
        total = conn.execute('SELECT COUNT(*) FROM billing_cases WHERE '+where,args).fetchone()[0]
        rows = [dict(r) for r in conn.execute('SELECT * FROM billing_cases WHERE '+where+
                ' ORDER BY updated_at DESC,case_id LIMIT ? OFFSET ?',[*args,limit,offset])]
        return {'cases':rows,'matched_cases':total,'next_offset':offset+limit if offset+limit<total else None,'note':NOTE}
