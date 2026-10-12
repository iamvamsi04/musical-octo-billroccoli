from fastmcp import FastMCP
from mcp_server.tools.database import execute_sql_query
from mcp_server.tools.billing_tools import request_order, place_order, apply_promotion, process_refund, download_invoice
from mcp_server.tools.analytics_tools import billing_analysis, billing_anomalies
from mcp_server.tools.support_tools import manage_billing_case, get_billing_cases
from mcp_server.tools.operations_tools import (manage_customer, manage_draft, set_invoice_due_date,
    manage_payment, issue_credit_note, billing_statement, manage_dispute, prepare_payment_reminder)

mcp = FastMCP("Billing tools")
TOOLS = (execute_sql_query, request_order, place_order, apply_promotion, process_refund, download_invoice,
         billing_analysis, billing_anomalies, manage_customer, manage_draft, set_invoice_due_date,
         manage_payment, issue_credit_note, billing_statement, manage_dispute, prepare_payment_reminder,
         manage_billing_case, get_billing_cases)
for tool in TOOLS:
    mcp.tool(tool)

if __name__ == "__main__":
    mcp.run(transport="stdio", show_banner=False)
