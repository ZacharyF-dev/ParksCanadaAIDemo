from __future__ import annotations

import json
import sys
from typing import Any

import chainlit as cl

from jira_foundry_agent.agent import run_agent
from jira_foundry_agent.settings import settings


@cl.on_chat_start
async def start() -> None:
    await cl.Message(
        content=(
            "Connected to the local JiraLite MCP server. Azure AI Foundry is used only "
            "for model inference. Tool calls appear below each response as expandable steps."
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

        step = steps.get(key)
        if step is None:
            step = cl.Step(name=f"MCP tool: {name}", type="tool")
            await step.send()
        step.output = result
        await step.update()

    answer = cl.Message(content="")
    try:
        answer.content = await run_agent(message.content, report_tool_activity)
    except RuntimeError as exc:
        answer.content = f"Configuration error: {exc}"
    except Exception as exc:
        answer.content = f"Agent request failed: {exc}"
    await answer.send()


def main() -> None:
    """Start Chainlit through its CLI for the installed console experience."""
    from chainlit.cli import run_chainlit

    sys.argv = [
        "chainlit",
        "run",
        __file__,
        "--host",
        settings.host,
        "--port",
        str(settings.port),
    ]
    run_chainlit()