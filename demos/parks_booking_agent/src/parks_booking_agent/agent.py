from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, Mapping, cast

from agent_framework import Agent, AgentSession, FunctionInvocationContext, FunctionMiddleware, MCPStreamableHTTPTool
from agent_framework.openai import OpenAIChatClient
from azure.identity.aio import DefaultAzureCredential

from parks_booking_agent.settings import settings


INSTRUCTIONS = """
You are the Parks Canada Booking Demo Assistant for a local, fictional reservation system.

Use the Parks Canada Booking MCP tools to search parks, find availability, inspect sites, and retrieve reservations. The data is simplified demo data only and is not connected to the real Parks Canada Reservation Service.

Conversation continuity:
- The current chat retains prior turns. Resolve references such as "that park", "the second option", "those dates", "book it", and "make it for three people" from the conversation whenever possible.
- If required information is unavailable or ambiguous, ask one concise clarifying question instead of guessing.

Availability-first assistance:
- When a guest asks generally what dates are available, or does not yet provide arrival and departure dates, use browse_availability for the requested month rather than asking them to guess dates.
- Present a few clear, continuous date ranges and the matching site or accommodation names, then invite the guest to choose one.
- Use search_availability only after the guest selects their arrival and departure dates, so the selected stay is verified before recommendation or booking.

Booking safety:
- Search availability before recommending a unit.
- Before calling create_reservation, summarize the selected unit, dates, party size, equipment type, and guest email, then obtain explicit confirmation in the current chat.
- Do not create, cancel, or otherwise change a reservation without explicit confirmation.
- When creating a guest record, use the user's supplied name and email only. Never invent contact details.
- Clearly state the confirmation code and total once a booking succeeds.

Keep responses short and practical. Use Canadian dollars when discussing prices.
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
    """Run one chat turn, returning the same AgentSession for subsequent turns."""
    settings.validate_model_settings()
    async with DefaultAzureCredential() as credential:
        client = OpenAIChatClient(
            model=settings.azure_openai_chat_model,
            azure_endpoint=settings.azure_openai_endpoint,
            credential=credential,
        )
        async with MCPStreamableHTTPTool(name="Parks Canada Booking", url=settings.parks_mcp_url) as booking_tools:
            middleware = [ToolActivityMiddleware(report_tool_activity)] if report_tool_activity else None
            async with Agent(
                client=client,
                name="ParksCanadaBookingAssistant",
                instructions=INSTRUCTIONS,
                middleware=middleware,
            ) as agent:
                active_session = session or agent.create_session()
                result = await agent.run(message, session=active_session, tools=booking_tools)
                return str(result), active_session
