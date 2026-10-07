from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, Mapping, cast

from agent_framework import Agent, FunctionInvocationContext, FunctionMiddleware, FunctionTool, MCPStreamableHTTPTool
from agent_framework.openai import OpenAIChatClient
from azure.identity.aio import DefaultAzureCredential

from app.time_tools import get_current_local_time
from jira_foundry_agent.settings import settings

INSTRUCTIONS = """
You are the JiraLite assistant. JiraLite tools are available through a local MCP server.
Use those tools for Jira facts and changes; never invent ticket data. Use the current-time tool when asked for the current date or time, and state that it reports the server's local time including its UTC offset. Before any mutation,
archive, escalation, or bulk operation, ask the user for explicit confirmation and do not
call a mutating tool until they confirm. For successful tool actions, state what changed.
Keep answers concise and identify ticket IDs or keys when available.
""".strip()


ToolActivityCallback = Callable[[str, dict[str, Any], str | None], Awaitable[None]]


class ToolActivityMiddleware(FunctionMiddleware):
    """Reports actual Agent Framework function executions to the presentation layer."""

    def __init__(self, report: ToolActivityCallback) -> None:
        self.report = report

    async def process(
        self,
        context: FunctionInvocationContext,
        call_next: Callable[[], Awaitable[None]],
    ) -> None:
        model_dump = getattr(context.arguments, "model_dump", None)
        raw_arguments = model_dump() if callable(model_dump) else context.arguments
        arguments = dict(cast(Mapping[str, Any], raw_arguments))
        await self.report(context.function.name, arguments, None)
        await call_next()
        await self.report(context.function.name, arguments, str(context.result))


async def run_agent(message: str, report_tool_activity: ToolActivityCallback | None = None) -> str:
    """Run one local agent turn, using Foundry only for model inference."""
    settings.validate_model_settings()

    async with DefaultAzureCredential() as credential:
        client = OpenAIChatClient(
            model=settings.azure_openai_chat_model,
            azure_endpoint=settings.azure_openai_endpoint,
            credential=credential,
        )
        async with MCPStreamableHTTPTool(
            name="JiraLite",
            url=settings.jira_mcp_url,
        ) as jira_tools:
            middleware = [ToolActivityMiddleware(report_tool_activity)] if report_tool_activity else None
            async with Agent(
                client=client,
                name="JiraLiteAssistant",
                instructions=INSTRUCTIONS,
                middleware=middleware,
            ) as agent:
                current_time_tool = FunctionTool(
                    name="get_current_local_time",
                    description="Get the server's current local date and time with its UTC offset.",
                    func=get_current_local_time,
                )
                result = await agent.run(message, tools=[jira_tools, current_time_tool])
                return str(result)
