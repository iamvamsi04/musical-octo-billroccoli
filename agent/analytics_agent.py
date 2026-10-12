"""Compatibility entry point; the primary agent now includes all billing workflows."""
from agent.billing_agent import BillingAgent, RecordingWorkbench, parameters
from agent.system_message import SYSTEM_MESSAGE

ANALYTICS_MESSAGE = SYSTEM_MESSAGE


class AnalyticsWorkbench(RecordingWorkbench):
    def __init__(self):
        extended = parameters().model_copy(update={"args": ["-m", "mcp_server.server_analytics"]})
        super().__init__(extended)


class AnalyticsBillingAgent(BillingAgent):
    system_message = SYSTEM_MESSAGE
    workbench_factory = AnalyticsWorkbench
