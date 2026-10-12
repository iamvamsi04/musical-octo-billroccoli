import asyncio
import json

import pytest
from autogen_core import FunctionCall
from autogen_core.models import CreateResult, RequestUsage
from autogen_ext.models.replay import ReplayChatCompletionClient

import agent.billing_agent as module
from agent.analytics_agent import AnalyticsBillingAgent
from database.connection import transaction
from mcp_server.tools.billing_tools import request_order, place_order


def tool_call(name, **arguments):
    return CreateResult(finish_reason="function_calls", content=[FunctionCall(
        id="1", name=name, arguments=json.dumps(arguments))],
        usage=RequestUsage(prompt_tokens=0, completion_tokens=0), cached=False)


@pytest.mark.parametrize("engine_type", [module.BillingAgent, AnalyticsBillingAgent])
def test_reuse_fresh_data_and_separate_contexts(monkeypatch, engine_type):
    class CapturingReplay(ReplayChatCompletionClient):
        async def create(self, messages, **kwargs):
            inputs.append(list(messages))
            return await super().create(messages, **kwargs)

    inputs, clients = [], []
    replay = CapturingReplay([
        tool_call("execute_sql_query", query="SELECT COUNT(*) FROM customers"), "4 customers.",
        tool_call("execute_sql_query", query="SELECT COUNT(*) FROM customers"), "5 customers."])
    def client():
        clients.append(replay)
        return replay
    monkeypatch.setattr(module, "create_model_client", client)

    async def run():
        engine = engine_type()
        await engine.start()
        workbench = engine._workbench
        actor = workbench._actor
        try:
            await engine.chat("First private question", [{"role": "user", "content": "Private history"}], "CUST001")
            with transaction() as conn:
                conn.execute("INSERT INTO customers(customer_id,name) VALUES ('NEW','New customer')")
            await engine.chat("Second question", [], "CUST002")
            assert len(clients) == 1
            assert engine._workbench is workbench and workbench._actor is actor
            assert "Private history" not in str(inputs[2])
            assert "CUST001" not in str(inputs[2])
            assert "CUST002" in str(inputs[2])
            assert "[[5]]" in str(inputs[3])  # Actual fresh MCP result, not the replay answer.
            schemas = await workbench.list_tools()
            schemas.clear()
            from mcp_server.server import TOOLS
            assert len(await workbench.list_tools()) == len(TOOLS)
        finally:
            await engine.close()
        assert engine._client is None and engine._workbench is None
        assert workbench._actor is None
    asyncio.run(run())


def test_invoice_attachments_do_not_leak_between_turns(monkeypatch):
    order = request_order("CUST001", [{"item_code": "ITEM001", "quantity": 1}])
    invoice = place_order(order["order_id"], "CUST001")["invoice_number"]
    replay = ReplayChatCompletionClient([
        tool_call("download_invoice", invoice_number=invoice, customer_id="CUST001"),
        "Your invoice is ready.", "Hello."])
    monkeypatch.setattr(module, "create_model_client", lambda: replay)

    async def run():
        engine = module.BillingAgent()
        await engine.start()
        try:
            first = await engine.chat("Invoice please", [], "CUST001")
            second = await engine.chat("Hello", [], "CUST002")
            assert first["invoices"] == [{"invoice_number": invoice, "customer_id": "CUST001"}]
            assert second["invoices"] == []
        finally:
            await engine.close()
    asyncio.run(run())


@pytest.mark.parametrize("cancelled", [False, True])
def test_failed_turn_discards_resources_without_replaying(monkeypatch, cancelled):
    class BrokenReplay(ReplayChatCompletionClient):
        async def create(self, *args, **kwargs):
            if cancelled:
                raise asyncio.CancelledError()
            raise RuntimeError("Unavailable")

    created = []
    def client():
        replay = BrokenReplay([]) if not created else ReplayChatCompletionClient(["Recovered."])
        created.append(replay)
        return replay
    monkeypatch.setattr(module, "create_model_client", client)

    async def run():
        engine = module.BillingAgent()
        await engine.start()
        original = engine._workbench
        try:
            with pytest.raises(asyncio.CancelledError if cancelled else RuntimeError):
                await engine.chat("Fail", [], None)
            assert len(created) == 1
            assert engine._client is None and engine._workbench is None
            assert original._actor is None
            assert (await engine.chat("New turn", [], None))["response"] == "Recovered."
            assert len(created) == 2
        finally:
            await engine.close()
    asyncio.run(run())
