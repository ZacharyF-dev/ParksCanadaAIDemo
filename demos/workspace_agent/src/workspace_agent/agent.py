from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, Mapping, cast

from agent_framework import Agent, AgentSession, FunctionInvocationContext, FunctionMiddleware, FunctionTool, MCPStreamableHTTPTool
from agent_framework.openai import OpenAIChatClient
from azure.identity.aio import DefaultAzureCredential

from app.time_tools import get_current_local_time
from workspace_agent.settings import settings

INSTRUCTIONS = """
You are the Local Workspace Assistant. You can use three local MCP services:
- JiraLite: ticket information and ticket operations.
- Markdown Knowledge: semantic search across locally indexed Markdown documents.
- Synthetic PC411 Directory: fictional organization and contact data only.
- Current local time: the server's current local date and time, including its UTC offset.

Use the relevant tool instead of inventing facts. Use the current-time tool when asked for the current date or time. Cite ticket IDs/keys, Markdown source paths,
and synthetic directory emails when available. Never represent the directory's synthetic people
as real employees. Before Jira mutations, archiving, escalation, or bulk updates, request explicit
user confirmation and do not invoke the mutation until confirmed.
""".strip()

ToolActivityCallback = Callable[[str, dict[str, Any], str | None], Awaitable[None]]


class ToolActivityMiddleware(FunctionMiddleware):
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


async def run_agent(
    message: str,
    session: AgentSession | None = None,
    report_tool_activity: ToolActivityCallback | None = None,
) -> tuple[str, AgentSession]:
    settings.validate_model_settings()
    async with DefaultAzureCredential() as credential:
        client = OpenAIChatClient(
            model=settings.azure_openai_chat_model,
            azure_endpoint=settings.azure_openai_endpoint,
            credential=credential,
        )
        async with (
            MCPStreamableHTTPTool(name="JiraLite", url=settings.jira_mcp_url) as jira_tools,
            MCPStreamableHTTPTool(name="Markdown Knowledge", url=settings.rag_mcp_url) as rag_tools,
            MCPStreamableHTTPTool(name="Synthetic PC411 Directory", url=settings.directory_mcp_url) as directory_tools,
        ):
            middleware = [ToolActivityMiddleware(report_tool_activity)] if report_tool_activity else None
            async with Agent(
                client=client,
                name="LocalWorkspaceAssistant",
                instructions=INSTRUCTIONS,
                middleware=middleware,
            ) as agent:
                active_session = session or agent.create_session()
                current_time_tool = FunctionTool(
                    name="get_current_local_time",
                    description="Get the server's current local date and time with its UTC offset.",
                    func=get_current_local_time,
                )
                result = await agent.run(
                    message,
                    session=active_session,
                    tools=[jira_tools, rag_tools, directory_tools, current_time_tool],
                )
                return str(result), active_session
