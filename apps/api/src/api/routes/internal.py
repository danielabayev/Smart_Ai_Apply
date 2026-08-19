"""Internal, agent-facing endpoints (api-structure-en.md section 1.6).

Not exposed to the end user - called by Agent 4 (Evaluation) and
Agent 5 (Tailoring) to create/update Applications.
"""

import logging
import uuid

from flask import Blueprint, abort, jsonify, request

from api.extensions import db
from api.models import Application

logger = logging.getLogger(__name__)

internal_bp = Blueprint("internal", __name__)


@internal_bp.post("/internal/applications")
def create_application():
    """Called by Agent 4 when a match crosses the user's match_threshold."""
    body = request.get_json(silent=True) or {}
    for field in ("user_id", "job_id", "match_score"):
        if field not in body:
            abort(400, description=f"'{field}' is required")

    try:
        user_uuid = uuid.UUID(body["user_id"])
    except ValueError:
        abort(400, description="Invalid user_id")

    application = Application(
        user_id=user_uuid,
        job_id=body["job_id"],
        match_score=body["match_score"],
        status="pending_tailoring",
    )
    db.session.add(application)
    db.session.commit()
    logger.info(
        "Agent 4 created application id=%s user_id=%s job_id=%s match_score=%s",
        application.id,
        application.user_id,
        application.job_id,
        application.match_score,
    )
    return jsonify(application.to_dict()), 201


@internal_bp.patch("/internal/applications/<application_id>")
def update_application(application_id: str):
    """Called by Agent 5 with the generated tailored resume."""
    try:
        app_uuid = uuid.UUID(application_id)
    except ValueError:
        abort(404, description="Application not found")

    application = db.session.get(Application, app_uuid)
    if application is None:
        abort(404, description="Application not found")

    body = request.get_json(silent=True) or {}
    if "document_content" in body:
        application.document_content = body["document_content"]
    application.status = "pending_approval"
    db.session.commit()
    logger.info("Agent 5 updated application id=%s -> pending_approval", application.id)
    return jsonify(application.to_dict())
