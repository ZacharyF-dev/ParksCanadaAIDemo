from __future__ import annotations

import json
import sys
from typing import Any

import chainlit as cl
from agent_framework import AgentSession

from workspace_agent.agent import run_agent
from workspace_agent.settings import settings


@cl.on_chat_start
async def start() -> None:
    cl.user_session.set("agent_session", None)
    await cl.Message(
        content=(
            "**Local Workspace Assistant** is connected to JiraLite, Markdown Knowledge, and the "
            "synthetic PC411 Directory. Azure AI Foundry is used only for inference. "
            "Every tool call is shown below the response as an expandable step."
        )
    ).send()


@cl.on_message
async def handle_message(message: cl.Message) -> None:
    steps: dict[tuple[str, str], cl.Step] = {}

    async def report_tool_activity(name: str, arguments: dict[str, Any], result: str | None) -> None:
        key = (name, json.dumps(arguments, sort_keys=True, default=str))
        if result is None:
            step = cl.Step(name=f"MCP tool: {name}", type="tool")
            step.input = json.dumps(arguments, indent=2, default=str)
            await step.send()
            steps[key] = step
            return
        step = steps.get(key) or cl.Step(name=f"MCP tool: {name}", type="tool")
        if key not in steps:
            await step.send()
        step.output = result
        await step.update()

    answer = cl.Message(content="")
    try:
        session = cl.user_session.get("agent_session")
        answer.content, session = await run_agent(
            message.content,
            session=session if isinstance(session, AgentSession) else None,
            report_tool_activity=report_tool_activity,
        )
        cl.user_session.set("agent_session", session)
    except RuntimeError as exc:
        answer.content = f"Configuration error: {exc}"
    except Exception as exc:
        answer.content = f"Agent request failed: {exc}"
    await answer.send()


def main() -> None:
    from chainlit.cli import run_chainlit

    sys.argv = ["chainlit", "run", __file__, "--host", settings.host, "--port", str(settings.port)]
    run_chainlit()
