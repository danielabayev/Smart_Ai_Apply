"""Conversation endpoints (api-structure-en.md section 1.3)."""

import logging
import time
import uuid

from flask import Blueprint, abort, jsonify, request

from api.agent_client import get_agent_reply
from api.current_user import get_current_user
from api.extensions import db
from api.models import Conversation, Message

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
    return jsonify(conversation.to_dict()), 201


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
    body = request.get_json(silent=True) or {}
    content = body.get("content")
    if not content:
        abort(400, description="'content' is required")

    user_message = Message(conversation_id=conversation.id, sender="user", content=content)
    db.session.add(user_message)
    db.session.commit()

    history = [m.to_dict() for m in conversation.messages]

    started_at = time.monotonic()
    agent_result = get_agent_reply(
        conversation_id=str(conversation.id),
        conversation_type=conversation.type,
        message_history=history,
        user_message=content,
    )
    response_time_ms = int((time.monotonic() - started_at) * 1000)

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
            "building_blocks_created": agent_result.get("building_blocks_created", []),
            "building_blocks_updated": agent_result.get("building_blocks_updated", []),
        }
    )


@conversations_bp.post("/conversations/<conversation_id>/finish")
def finish_conversation(conversation_id: str):
    conversation = _get_conversation_or_404(conversation_id)
    conversation.status = "finished"
    db.session.commit()
    logger.info("Finished conversation_id=%s", conversation.id)
    return jsonify(conversation.to_dict())
