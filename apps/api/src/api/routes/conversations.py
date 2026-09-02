"""Conversation endpoints (api-structure-en.md section 1.3)."""

import logging
import time
import uuid
from typing import Any

from flask import Blueprint, abort, jsonify, request

from api.agent_client import get_agent_reply
from api.current_user import get_current_user
from api.extensions import db
from api.job_scan_cursor import reset_job_scan_cursor
from api.models import Application, BuildingBlock, Company, Conversation, Job, Message, User

logger = logging.getLogger(__name__)

conversations_bp = Blueprint("conversations", __name__)


def _get_conversation_or_404(conversation_id: str) -> Conversation:
    try:
        conv_uuid = uuid.UUID(conversation_id)
    except ValueError:
        abort(404, description="Conversation not found")
    conversation = db.session.get(Conversation, conv_uuid)
    if conversation is None:
        abort(404, description="Conversation not found")
    return conversation


def _build_context(conversation: Conversation, user: User) -> dict[str, Any]:
    """Pre-loads everything Agent 1 could need for this turn (wire contract section 3)."""
    context: dict[str, Any] = {
        "existing_building_blocks": None,
        "target_building_block": None,
        "job": None,
    }

    if conversation.type == "profiling":
        blocks = BuildingBlock.query.filter_by(user_id=user.id).all()
        context["existing_building_blocks"] = [b.to_dict() for b in blocks]
        return context

    # 'refinement' and 'application_edit' both reference the block being reworded/replaced.
    if conversation.building_block_id is not None:
        block = db.session.get(BuildingBlock, conversation.building_block_id)
        if block is None:
            abort(500, description="Conversation references a missing building_block_id")
        context["target_building_block"] = block.to_dict()

    if conversation.type == "application_edit":
        if conversation.application_id is None:
            abort(500, description="'application_edit' conversation missing application_id")
        application = db.session.get(Application, conversation.application_id)
        if application is None:
            abort(500, description="Conversation references a missing application_id")
        job = db.session.get(Job, application.job_id)
        if job is None:
            abort(500, description="Application references a missing job_id")
        job_dict = job.to_dict()
        job_dict.pop("discovered_at", None)
        job_dict.pop("updated_at", None)
        company = db.session.get(Company, job.company_id)
        job_dict["company"] = (
            {"id": company.id, "name": company.name, "website": company.website} if company else None
        )
        context["job"] = job_dict

    return context


def _persist_building_block_changes(
    conversation: Conversation, user: User, agent_result: dict[str, Any]
) -> tuple[list[dict], list[dict]]:
    """Writes Agent 1's created/updated blocks to the DB (the API Server is the sole writer)."""
    created_dicts: list[dict] = []
    updated_dicts: list[dict] = []
    changed = False

    for item in agent_result.get("building_blocks_created", []):
        block = BuildingBlock(
            user_id=user.id,
            conversation_id=conversation.id,
            category=item["category"],
            title=item["title"],
            content=item["content"],
            variants=item.get("variants", []),
        )
        db.session.add(block)
        db.session.flush()
        created_dicts.append(block.to_dict())
        changed = True

    for item in agent_result.get("building_blocks_updated", []):
        try:
            block_uuid = uuid.UUID(item["id"])
        except (KeyError, ValueError):
            logger.error("Agent 1 returned an invalid building_block id: %r", item.get("id"))
            abort(500, description="Agent returned an invalid building_block id")
        if conversation.building_block_id is not None and block_uuid != conversation.building_block_id:
            logger.error(
                "Agent 1 building_blocks_updated id=%s does not match conversation.building_block_id=%s",
                block_uuid,
                conversation.building_block_id,
            )
            abort(500, description="Agent returned a mismatched building_block id")
        block = db.session.get(BuildingBlock, block_uuid)
        if block is None:
            abort(500, description="Agent referenced a missing building_block id")
        block.category = item["category"]
        block.title = item["title"]
        block.content = item["content"]
        block.variants = item.get("variants", [])
        updated_dicts.append(block.to_dict())
        changed = True

    if changed:
        reset_job_scan_cursor(user.id)

    return created_dicts, updated_dicts


def _format_agent_result_for_logging(agent_result: dict[str, Any], max_value_len: int = 300) -> str:
    """Formats agent_result as one 'key: value' line per field, truncating long values."""
    lines = []
    for key, value in agent_result.items():
        text = repr(value)
        if len(text) > max_value_len:
            text = f"{text[:max_value_len]}... (truncated, {len(text)} chars total)"
        lines.append(f"{key}: {text}")
    return "\n".join(lines)


def _send_kickoff_message(conversation: Conversation, user: User) -> None:
    """Auto-triggers Agent 1's self-introduction for a fresh `profiling` conversation.

    Calls Agent 1 with an empty `user_message` and no history - the system-triggered
    kickoff signal (agent-structure-en.md section 5, `intro` phase) - so the agent
    introduces itself and explains the interview flow before the user types anything.
    """
    context = _build_context(conversation, user)
    started_at = time.monotonic()
    agent_result = get_agent_reply(
        conversation_id=str(conversation.id),
        conversation_type=conversation.type,
        message_history=[],
        user_message="",
        user_id=str(user.id),
        building_block_id=None,
        application_id=None,
        context=context,
    )
    response_time_ms = int((time.monotonic() - started_at) * 1000)

    if agent_result.get("building_blocks_created") or agent_result.get("building_blocks_updated"):
        logger.warning(
            "Agent 1 returned building block changes on the kickoff turn for conversation_id=%s "
            "(no history/user_message was sent, so this is unexpected - likely a hallucination or "
            "bug; discarding these changes without persisting them). Agent response:\n%s",
            conversation.id,
            _format_agent_result_for_logging(agent_result),
        )
    else:
        _persist_building_block_changes(conversation, user, agent_result)

    agent_message = Message(
        conversation_id=conversation.id,
        sender="agent",
        content=agent_result["reply"],
        response_time_ms=response_time_ms,
    )
    db.session.add(agent_message)
    db.session.commit()
    logger.info("Sent kickoff message for conversation_id=%s", conversation.id)


@conversations_bp.post("/conversations")
def create_conversation():
    user = get_current_user()
    body = request.get_json(silent=True) or {}
    conv_type = body.get("type", "profiling")

    conversation = Conversation(
        user_id=user.id,
        type=conv_type,
        building_block_id=body.get("building_block_id"),
        application_id=body.get("application_id"),
    )
    db.session.add(conversation)
    db.session.commit()
    logger.info("Created conversation id=%s type=%s user_id=%s", conversation.id, conv_type, user.id)

    if conv_type == "profiling":
        _send_kickoff_message(conversation, user)

    return jsonify(conversation.to_dict(include_messages=True)), 201


@conversations_bp.get("/conversations")
def list_conversations():
    user = get_current_user()
    conversations = (
        Conversation.query.filter_by(user_id=user.id).order_by(Conversation.created_at.desc()).all()
    )
    return jsonify([c.to_dict() for c in conversations])


@conversations_bp.get("/conversations/<conversation_id>")
def get_conversation(conversation_id: str):
    conversation = _get_conversation_or_404(conversation_id)
    return jsonify(conversation.to_dict(include_messages=True, include_building_blocks=True))


@conversations_bp.post("/conversations/<conversation_id>/messages")
def post_message(conversation_id: str):
    conversation = _get_conversation_or_404(conversation_id)
    user = get_current_user()
    body = request.get_json(silent=True) or {}
    content = body.get("content")
    if not content:
        abort(400, description="'content' is required")

    user_message = Message(conversation_id=conversation.id, sender="user", content=content)
    db.session.add(user_message)
    db.session.commit()

    history = [msg.to_dict() for msg in conversation.messages]
    context = _build_context(conversation, user)

    started_at = time.monotonic()
    agent_result = get_agent_reply(
        conversation_id=str(conversation.id),
        conversation_type=conversation.type,
        message_history=history,
        user_message=content,
        user_id=str(user.id),
        building_block_id=str(conversation.building_block_id) if conversation.building_block_id else None,
        application_id=str(conversation.application_id) if conversation.application_id else None,
        context=context,
    )
    response_time_ms = int((time.monotonic() - started_at) * 1000)

    created, updated = _persist_building_block_changes(conversation, user, agent_result)

    agent_message = Message(
        conversation_id=conversation.id,
        sender="agent",
        content=agent_result["reply"],
        response_time_ms=response_time_ms,
    )
    db.session.add(agent_message)
    db.session.commit()

    logger.info("Processed message in conversation_id=%s", conversation.id)

    return jsonify(
        {
            "agent_reply": agent_result["reply"],
            "building_blocks_created": created,
            "building_blocks_updated": updated,
        }
    )


@conversations_bp.post("/conversations/<conversation_id>/finish")
def finish_conversation(conversation_id: str):
    conversation = _get_conversation_or_404(conversation_id)
    conversation.status = "finished"
    db.session.commit()
    logger.info("Finished conversation_id=%s", conversation.id)
    return jsonify(conversation.to_dict())
