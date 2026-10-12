-- Additive migration. Original orders and invoice lines remain intact.
CREATE TABLE IF NOT EXISTS order_details (
    order_id TEXT PRIMARY KEY REFERENCES orders(order_id),
    status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','cancelled')),
    due_date TEXT,
    currency TEXT NOT NULL,
    customer_snapshot TEXT,
    cancellation_reason TEXT
);
CREATE TABLE IF NOT EXISTS payments (
    payment_id TEXT PRIMARY KEY,
    order_id TEXT NOT NULL REFERENCES orders(order_id),
    amount_cents INTEGER NOT NULL CHECK(amount_cents>0),
    currency TEXT NOT NULL,
    received_date TEXT NOT NULL,
    reference TEXT NOT NULL UNIQUE,
    method TEXT NOT NULL,
    reversed INTEGER NOT NULL DEFAULT 0 CHECK(reversed IN (0,1)),
    reversal_reason TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_payments_order ON payments(order_id,reversed);
CREATE TABLE IF NOT EXISTS credit_notes (
    credit_id TEXT PRIMARY KEY,
    order_id TEXT NOT NULL REFERENCES orders(order_id),
    amount_cents INTEGER NOT NULL CHECK(amount_cents>0),
    currency TEXT NOT NULL,
    reason TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_credits_order ON credit_notes(order_id);
CREATE TRIGGER IF NOT EXISTS credits_no_update BEFORE UPDATE ON credit_notes
BEGIN SELECT RAISE(ABORT, 'Issued credit notes cannot be updated'); END;
CREATE TRIGGER IF NOT EXISTS credits_no_delete BEFORE DELETE ON credit_notes
BEGIN SELECT RAISE(ABORT, 'Issued credit notes cannot be deleted'); END;
CREATE TABLE IF NOT EXISTS billing_disputes (
    dispute_id TEXT PRIMARY KEY,
    order_id TEXT NOT NULL REFERENCES orders(order_id),
    reason TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('open','resolved')),
    resolution TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    resolved_at TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS ix_one_open_dispute ON billing_disputes(order_id) WHERE status='open';
CREATE TABLE IF NOT EXISTS billing_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    action TEXT NOT NULL,
    details_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TRIGGER IF NOT EXISTS audit_no_update BEFORE UPDATE ON billing_audit
BEGIN SELECT RAISE(ABORT, 'Audit records cannot be updated'); END;
CREATE TRIGGER IF NOT EXISTS audit_no_delete BEFORE DELETE ON billing_audit
BEGIN SELECT RAISE(ABORT, 'Audit records cannot be deleted'); END;
CREATE INDEX IF NOT EXISTS ix_order_due ON order_details(due_date,status);
CREATE TABLE IF NOT EXISTS billing_cases (
    case_id TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL REFERENCES customers(customer_id),
    order_id TEXT REFERENCES orders(order_id),
    category TEXT NOT NULL CHECK(category IN ('invoice','payment','refund','dispute','order','account','other')),
    summary TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open','awaiting_customer','under_review','escalated','resolved','closed')),
    priority TEXT NOT NULL DEFAULT 'normal' CHECK(priority IN ('normal','urgent')),
    resolution TEXT,
    version INTEGER NOT NULL DEFAULT 1 CHECK(version>0),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_cases_customer ON billing_cases(customer_id,status,updated_at);
CREATE TABLE IF NOT EXISTS billing_case_events (
    event_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES billing_cases(case_id),
    action TEXT NOT NULL,
    note TEXT NOT NULL,
    source TEXT NOT NULL CHECK(source IN ('customer_reported','operator_verified')),
    resulting_status TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_case_events ON billing_case_events(case_id,created_at);
CREATE TRIGGER IF NOT EXISTS case_events_no_update BEFORE UPDATE ON billing_case_events
BEGIN SELECT RAISE(ABORT, 'Case events cannot be updated'); END;
CREATE TRIGGER IF NOT EXISTS case_events_no_delete BEFORE DELETE ON billing_case_events
BEGIN SELECT RAISE(ABORT, 'Case events cannot be deleted'); END;
