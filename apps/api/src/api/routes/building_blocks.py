"""Building block endpoints (api-structure-en.md section 1.4)."""

import logging
import uuid

from flask import Blueprint, abort, jsonify, request

from api.current_user import get_current_user
from api.extensions import db
from api.job_scan_cursor import reset_job_scan_cursor
from api.models import BuildingBlock, Conversation

logger = logging.getLogger(__name__)

building_blocks_bp = Blueprint("building_blocks", __name__)


def _get_block_or_404(block_id: str) -> BuildingBlock:
    try:
        block_uuid = uuid.UUID(block_id)
    except ValueError:
        abort(404, description="Building block not found")
    block = db.session.get(BuildingBlock, block_uuid)
    if block is None:
        abort(404, description="Building block not found")
    return block


@building_blocks_bp.get("/building-blocks")
def list_building_blocks():
    user = get_current_user()
    query = BuildingBlock.query.filter_by(user_id=user.id)

    conversation_id = request.args.get("conversation_id")
    if conversation_id:
        try:
            query = query.filter_by(conversation_id=uuid.UUID(conversation_id))
        except ValueError:
            abort(400, description="Invalid conversation_id")

    blocks = query.order_by(BuildingBlock.created_at.desc()).all()
    return jsonify([b.to_dict() for b in blocks])


@building_blocks_bp.get("/building-blocks/<block_id>")
def get_building_block(block_id: str):
    block = _get_block_or_404(block_id)
    return jsonify(block.to_dict())


@building_blocks_bp.patch("/building-blocks/<block_id>")
def update_building_block(block_id: str):
    block = _get_block_or_404(block_id)
    body = request.get_json(silent=True) or {}

    if "title" in body:
        block.title = body["title"]
    if "content" in body:
        block.content = body["content"]
    if "category" in body:
        block.category = body["category"]

    reset_job_scan_cursor(block.user_id)
    db.session.commit()
    logger.info("Updated building_block id=%s", block.id)
    return jsonify(block.to_dict())


@building_blocks_bp.delete("/building-blocks/<block_id>")
def delete_building_block(block_id: str):
    block = _get_block_or_404(block_id)
    user_id = block.user_id
    db.session.delete(block)
    reset_job_scan_cursor(user_id)
    db.session.commit()
    logger.info("Deleted building_block id=%s", block_id)
    return "", 204


@building_blocks_bp.post("/building-blocks/<block_id>/regenerate")
def regenerate_building_block(block_id: str):
    block = _get_block_or_404(block_id)
    conversation = Conversation(
        user_id=block.user_id,
        type="refinement",
        building_block_id=block.id,
    )
    db.session.add(conversation)
    db.session.commit()
    logger.info("Opened refinement conversation id=%s for building_block id=%s", conversation.id, block.id)
    return jsonify(conversation.to_dict()), 201
