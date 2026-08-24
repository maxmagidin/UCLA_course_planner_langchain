"""Thin Agent Chat Protocol surface for ASI:One/Agentverse.

This module is only an adapter. It keeps the planner graph and typed models as
the source of truth, so a web app, CLI, or Agentverse client can reuse them.
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from uuid import uuid4

from uagents import Agent, Context, Protocol
from uagents_core.contrib.protocols.chat import (
    ChatAcknowledgement,
    ChatMessage,
    TextContent,
    chat_protocol_spec,
)

from course_planner.graph import run_planner
from course_planner.intake import extract_profile


agent = Agent(
    name="ucla-course-planner",
    seed=os.getenv("ASI_AGENT_SEED", "set-a-production-seed-in-the-environment"),
    port=int(os.getenv("ASI_AGENT_PORT", "8001")),
    mailbox=True,
    publish_agent_details=True,
)
protocol = Protocol(spec=chat_protocol_spec)
sessions: dict[str, list[dict[str, str]]] = {}


def _text(message: ChatMessage) -> str:
    return "\n".join(item.text for item in message.content if isinstance(item, TextContent)).strip()


async def _send(ctx: Context, destination: str, text: str) -> None:
    await ctx.send(destination, ChatMessage(
        content=[TextContent(type="text", text=text)],
        msg_id=uuid4(),
        timestamp=datetime.now(timezone.utc),
    ))


@protocol.on_message(ChatMessage)
async def handle_chat(ctx: Context, sender: str, message: ChatMessage):
    await ctx.send(sender, ChatAcknowledgement(
        timestamp=datetime.now(timezone.utc), acknowledged_msg_id=message.msg_id
    ))
    text = _text(message)
    if not text:
        return
    conversation = sessions.setdefault(sender, [])
    conversation.append({"role": "user", "content": text})
    try:
        profile = await asyncio.to_thread(extract_profile, conversation)
    except Exception:
        await _send(ctx, sender, "I still need a complete profile: name, major, year, GPA, units completed, enrollment pass and opening time, term, and target unit range.")
        return
    result = await asyncio.to_thread(run_planner, profile, thread_id=sender)
    await _send(ctx, sender, result.report_markdown or "The planner could not produce a report. Please try again with a different term or fewer hard constraints.")


@protocol.on_message(ChatAcknowledgement)
async def handle_ack(ctx: Context, sender: str, message: ChatAcknowledgement):
    """The chat protocol requires an acknowledgement handler on both sides."""
    return


agent.include(protocol, publish_manifest=True)


if __name__ == "__main__":
    agent.run()
