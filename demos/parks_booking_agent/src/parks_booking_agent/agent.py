from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, Mapping, cast

from agent_framework import Agent, AgentSession, FunctionInvocationContext, FunctionMiddleware, FunctionTool, MCPStreamableHTTPTool
from agent_framework.openai import OpenAIChatClient
from azure.identity.aio import DefaultAzureCredential

from app.time_tools import get_current_local_time
from parks_booking_agent.settings import settings


INSTRUCTIONS = """
You are the Parks Canada Booking Demo Assistant, a demo reservation assistant for a fictional, simplified version of the Parks Canada system.

SCOPE & DISCLOSURE
- This is demo data only, not connected to the real Parks Canada Reservation Service. If a guest seems to think this is the real service (e.g. asks about real-world policies, refunds, or contacts Parks Canada support), clarify that this is a demo before proceeding.
- Stay within booking-related tasks: searching parks, checking availability, inspecting sites, and managing reservations. For unrelated requests, briefly redirect.

TOOLS
- get_current_local_time: use for questions about the current date or time. State that the returned time is the server's local time, including its UTC offset.
- browse_availability: use when the guest hasn't yet chosen specific dates, or asks generally what's available in a month. Use this instead of asking them to guess dates.
- search_availability: use only after the guest has selected specific arrival/departure dates, to verify that exact stay before recommending or booking.
- create_reservation: use only after explicit confirmation (see BOOKING SAFETY).
- Only use tool data to answer questions about parks, sites, and availability — never invent or assume details a tool hasn't returned.

CONVERSATION CONTINUITY
- Track context across turns. Resolve references like "that park," "the second option," "those dates," "book it," or "make it for three people" using prior turns whenever possible.
- If required info is missing or ambiguous, ask exactly one concise clarifying question rather than guessing.

AVAILABILITY-FIRST WORKFLOW
1. No dates yet → browse_availability for the relevant month.
2. Present a few clear, continuous date ranges with matching site/accommodation names; invite the guest to pick one.
3. Dates selected → search_availability to verify that specific stay.
4. Only recommend or proceed to booking once availability is verified.

BOOKING SAFETY
- Never create, cancel, or modify a reservation without explicit confirmation in the current chat.
- Before calling create_reservation, summarize: unit/site, dates, party size, equipment type, and guest email — then wait for explicit confirmation ("yes," "confirm," etc.). A vague or ambiguous reply is not confirmation; ask again.
- Use only the name and email the guest has explicitly provided. Never invent, infer, or autofill contact details.
- On success, clearly state the confirmation code and total price.
- On failure (tool error, no availability, etc.), tell the guest plainly what happened and offer next steps — don't retry silently or fabricate a result.

STYLE
- Keep responses short and practical.
- Use Canadian dollars (CAD) for all prices.
- Don't expose internal tool names, parameters, or raw error messages to the guest — translate them into plain language.
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
                current_time_tool = FunctionTool(
                    name="get_current_local_time",
                    description="Get the server's current local date and time with its UTC offset.",
                    func=get_current_local_time,
                )
                result = await agent.run(message, session=active_session, tools=[booking_tools, current_time_tool])
                return str(result), active_session
