"""HTTP client for Agent 1 (Profiling), the LangGraph conversation agent.

Calls the standalone profiler-agent microservice (see `agents/profiler_agent`)
synchronously, per agent-structure-en.md sections 2-3: single request/response,
no streaming, no retry. On any failure this raises, which surfaces as a 500 to
the caller and halts the request - no silent recovery or degraded continuation
(Initial_prompt.txt's error-handling requirement).
"""

import logging
from typing import Any

import requests
from flask import current_app

logger = logging.getLogger(__name__)


def get_agent_reply(
    conversation_id: str,
    conversation_type: str,
    message_history: list[dict[str, Any]],
    user_message: str,
    user_id: str | None = None,
    building_block_id: str | None = None,
    application_id: str | None = None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Invokes Agent 1 for the next reply and any building block changes.

    Args:
        conversation_id (str): The conversation this message belongs to.
        conversation_type (str): One of 'profiling', 'refinement', 'application_edit'.
        message_history (list[dict[str, Any]]): Prior messages in the conversation.
        user_message (str): The new message from the user.
        user_id (str | None): The user this conversation belongs to (for tracing only).
        building_block_id (str | None): Reference block id, per conversation type.
        application_id (str | None): Reference application id, for 'application_edit'.
        context (dict[str, Any] | None): Pre-loaded context - `existing_building_blocks`,
            `target_building_block`, `job` (agent-structure-en.md section 3). Missing keys
            default to `None`.

    Returns:
        dict[str, Any]: Shape: {"reply": str, "building_blocks_created": list,
        "building_blocks_updated": list}.

    Raises:
        RuntimeError: If the profiler-agent call fails or returns a non-2xx status.
    """
    context = context or {}
    payload = {
        "conversation_id": conversation_id,
        "conversation_type": conversation_type,
        "user_id": user_id,
        "message_history": message_history,
        "user_message": user_message,
        "building_block_id": building_block_id,
        "application_id": application_id,
        "context": {
            "existing_building_blocks": context.get("existing_building_blocks"),
            "target_building_block": context.get("target_building_block"),
            "job": context.get("job"),
        },
    }

    url = f"{current_app.config['PROFILER_AGENT_URL']}/reply"
    try:
        response = requests.post(
            url, json=payload, timeout=current_app.config["PROFILER_AGENT_TIMEOUT_SECONDS"]
        )
    except requests.RequestException as exc:
        logger.error("profiler-agent request failed for conversation_id=%s: %s", conversation_id, exc)
        raise RuntimeError(f"profiler-agent request failed: {exc}") from exc

    if response.status_code >= 400:
        logger.error(
            "profiler-agent returned status=%s for conversation_id=%s: %s",
            response.status_code,
            conversation_id,
            response.text,
        )
        raise RuntimeError(f"profiler-agent returned {response.status_code}: {response.text}")

    return response.json()
