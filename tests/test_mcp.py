import asyncio
import json
from autogen_ext.tools.mcp import McpWorkbench
from agent.billing_agent import parameters, decode_result


def test_real_mcp_discovery_and_billing_flow():
    async def run():
        async with McpWorkbench(parameters()) as wb:
            tools = await wb.list_tools()
            from mcp_server.server import TOOLS
            assert {t["name"] for t in tools} == {t.__name__ for t in TOOLS}
            async def call(name, **args):
                result = decode_result(await wb.call_tool(name, args))
                assert result.get("ok"), result
                return result
            assert (await call("execute_sql_query", query="SELECT COUNT(*) FROM customers"))["rows"] == [[4]]
            order = await call("request_order", customer_id="CUST001", items=[{"item_code": "ITEM001", "quantity": 1}])
            await call("apply_promotion", order_id=order["order_id"], customer_id="CUST001", promo_code="SAVE10")
            placed = await call("place_order", order_id=order["order_id"], customer_id="CUST001")
            statement = await call('billing_statement', order_id=order['order_id'], customer_id='CUST001')
            assert statement['matched_invoices'] == 1
            await call('manage_payment', action='record', order_id=order['order_id'], customer_id='CUST001',
                       payment_id='MCP-PAY-1', amount='10.00', currency='USD', reference='MCP-BANK-1', confirmed=True)
            assert (await call('billing_analysis'))['invoice_count'] == 1
            assert (await call('billing_anomalies'))['finding_count'] == 0
            await call('manage_billing_case', action='create',case_id='CASE-MCP',customer_id='CUST001',
                       event_id='EVENT-MCP',note='Customer requests a refund timeline',category='refund',confirmed=True)
            case = await call('get_billing_cases',customer_id='CUST001',case_id='CASE-MCP')
            assert case['case']['status'] == 'open' and case['events'][0]['source'] == 'customer_reported'
            await call("process_refund", order_id=order["order_id"], customer_id="CUST001", reason="Test return")
            assert (await call("download_invoice", invoice_number=placed["invoice_number"], customer_id="CUST001"))["ready"]
    asyncio.run(run())


def test_autogen_tool_execution_and_reflection(monkeypatch):
    from autogen_core import FunctionCall
    from autogen_core.models import CreateResult, RequestUsage
    from autogen_ext.models.replay import ReplayChatCompletionClient
    import agent.billing_agent as module
    replay = ReplayChatCompletionClient([
        CreateResult(finish_reason="function_calls", content=[FunctionCall(id="1", name="execute_sql_query", arguments=json.dumps({"query": "SELECT COUNT(*) FROM customers"}))], usage=RequestUsage(prompt_tokens=0, completion_tokens=0), cached=False),
        "There are 4 customers in the billing database."])
    monkeypatch.setattr(module, "create_model_client", lambda: replay)
    result = asyncio.run(module.BillingAgent().chat("How many customers?", [], None))
    assert result["response"] == "There are 4 customers in the billing database."


def test_autogen_invoice_attachment(monkeypatch):
    from autogen_core import FunctionCall
    from autogen_core.models import CreateResult, RequestUsage
    from autogen_ext.models.replay import ReplayChatCompletionClient
    from mcp_server.tools.billing_tools import request_order, place_order
    import agent.billing_agent as module
    order = request_order("CUST001", [{"item_code": "ITEM001", "quantity": 1}])
    invoice = place_order(order["order_id"], "CUST001")["invoice_number"]
    replay = ReplayChatCompletionClient([
        CreateResult(finish_reason="function_calls", content=[FunctionCall(id="1", name="download_invoice", arguments=json.dumps({"invoice_number": invoice, "customer_id": "CUST001"}))], usage=RequestUsage(prompt_tokens=0, completion_tokens=0), cached=False),
        "Your invoice is ready."])
    monkeypatch.setattr(module, "create_model_client", lambda: replay)
    result = asyncio.run(module.BillingAgent().chat("Download my invoice", [], "CUST001"))
    assert result["invoices"] == [{"invoice_number": invoice, "customer_id": "CUST001"}]
