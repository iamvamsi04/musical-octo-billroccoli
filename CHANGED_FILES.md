# Operational billing update

Cumulative changes since the version before the operational workflows. The normal app.py entry point now serves eighteen tools. See WORKFLOWS.md and CUSTOMER_CONVERSATIONS.md for upgrade steps, examples and limitations.

## Modified files

- `agent/analytics_agent.py`
- `agent/billing_agent.py`
- `agent/system_message.py`
- `ANALYTICS.md`
- `database/connection.py`
- `database/invoice.py`
- `mcp_server/server.py`
- `mcp_server/server_analytics.py`
- `mcp_server/tools/analytics_tools.py`
- `mcp_server/tools/billing_tools.py`
- `mcp_server/tools/database.py`
- `TESTING.md`
- `tests/test_agent_lifecycle.py`
- `tests/test_mcp.py`
- `ui/streamlit_app.py`

## Added files

- `agent/conversation_policy.py`
- `CUSTOMER_CONVERSATIONS.md`
- `database/ledger.py`
- `database/operations.sql`
- `mcp_server/tools/operations_tools.py`
- `mcp_server/tools/support_tools.py`
- `tests/test_operations.py`
- `tests/test_support.py`
- `WORKFLOWS.md`
- `CHANGED_FILES.md`

The technology dependencies and API routes are unchanged. UI appearance is unchanged; its HTTP client now persists. Database changes are additive and run on API startup. The supplied original database was not modified during verification. The source ZIP excludes database files, invoice PDFs, local .env, caches and virtual environments.
