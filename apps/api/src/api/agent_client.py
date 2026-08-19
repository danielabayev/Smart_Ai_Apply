"""Placeholder client for Agent 1 (Profiling), the LangGraph conversation agent.

The actual agent lives outside this Flask app (see the top-level
`agents/` package) and is not wired up yet. This module isolates the
integration point so the real call can be dropped in later without
touching the route layer.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


def get_agent_reply(
    conversation_id: str, conversation_type: str, message_history: list[dict[str, Any]], user_message: str
) -> dict[str, Any]:
    """Invokes Agent 1 for the next reply and any building block changes.

    Args:
        conversation_id (str): The conversation this message belongs to.
        conversation_type (str): One of 'profiling', 'refinement', 'application_edit'.
        message_history (list[dict[str, Any]]): Prior messages in the conversation.
        user_message (str): The new message from the user.

    Returns:
        dict[str, Any]: Shape: {"reply": str, "building_blocks_created": list,
        "building_blocks_updated": list}.
    """
    logger.warning(
        "Agent 1 is not wired up yet; returning a stub reply for conversation_id=%s", conversation_id
    )
    return {
        "reply": "TODO: Agent 1 integration is not implemented yet.",
        "building_blocks_created": [],
        "building_blocks_updated": [],
    }
