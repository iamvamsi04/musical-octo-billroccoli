"""SQLite parser/authorizer is the security boundary, not a keyword regex."""
import sqlite3
import time
from config import settings
from database.connection import connect

TABLES = {'billing_config', 'customers', 'items', 'promotions', 'orders',
          'order_requests', 'order_fulfilled', 'invoice_lines', 'price_history',
          'order_details', 'payments', 'credit_notes', 'billing_disputes', 'billing_audit',
          'billing_cases', 'billing_case_events'}
FUNCTIONS = set('abs avg coalesce count date datetime glob group_concat hex ifnull '
                'instr julianday length like lower ltrim max min nullif printf replace '
                'round rtrim strftime substr substring sum time total trim typeof '
                'unicode upper row_number rank dense_rank lag lead first_value last_value'.split())


def authorize(action, arg1, arg2, db, trigger):
    if action in (sqlite3.SQLITE_SELECT, sqlite3.SQLITE_RECURSIVE):
        return sqlite3.SQLITE_OK
    if action == sqlite3.SQLITE_READ and arg1 in TABLES and db in ('main', None):
        return sqlite3.SQLITE_OK
    if action == sqlite3.SQLITE_FUNCTION and (arg2 or '').lower() in FUNCTIONS:
        return sqlite3.SQLITE_OK
    if action == sqlite3.SQLITE_PRAGMA and arg1 == 'table_info' and arg2 in TABLES:
        return sqlite3.SQLITE_OK
    return sqlite3.SQLITE_DENY


def execute_sql_query(query: str) -> dict:
    """Read billing tables with one SELECT/WITH or PRAGMA table_info(table). Max rows apply."""
    if not isinstance(query, str) or not query.strip() or len(query) > 20000:
        return {'ok': False, 'error': 'Provide one SQL query of at most 20000 characters.'}
    conn = connect(readonly=True)
    try:
        conn.execute('PRAGMA query_only=ON')
        conn.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, 1000000)
        conn.setlimit(sqlite3.SQLITE_LIMIT_SQL_LENGTH, 20000)
        conn.setlimit(sqlite3.SQLITE_LIMIT_COLUMN, 100)
        deadline = time.monotonic() + 2
        conn.set_progress_handler(lambda: int(time.monotonic() > deadline), 1000)
        conn.set_authorizer(authorize)
        cursor = conn.execute(query)
        rows = cursor.fetchmany(settings.SQL_MAX_ROWS + 1)
        return {'ok': True, 'columns': [c[0] for c in cursor.description or []],
                'rows': [list(row) for row in rows[:settings.SQL_MAX_ROWS]],
                'row_count': min(len(rows), settings.SQL_MAX_ROWS),
                'truncated': len(rows) > settings.SQL_MAX_ROWS}
    except sqlite3.Error as exc:
        return {'ok': False, 'error': f'Query rejected or failed: {exc}'}
    finally:
        conn.close()
