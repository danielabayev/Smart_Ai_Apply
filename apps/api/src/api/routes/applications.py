"""Application endpoints (api-structure-en.md section 1.5)."""

import io
import logging
import uuid

from flask import Blueprint, abort, jsonify, request, send_file

from api.current_user import get_current_user
from api.extensions import db
from api.models import Application, Conversation
from api.queue_client import publish

logger = logging.getLogger(__name__)

applications_bp = Blueprint("applications", __name__)

_VALID_STATUSES = {"pending_tailoring", "pending_approval", "approved", "rejected"}


def _get_application_or_404(application_id: str) -> Application:
    try:
        app_uuid = uuid.UUID(application_id)
    except ValueError:
        abort(404, description="Application not found")
    application = db.session.get(Application, app_uuid)
    if application is None:
        abort(404, description="Application not found")
    return application


@applications_bp.get("/applications")
def list_applications():
    user = get_current_user()
    query = Application.query.filter_by(user_id=user.id)

    status = request.args.get("status")
    if status:
        if status not in _VALID_STATUSES:
            abort(400, description=f"Invalid status. Must be one of {sorted(_VALID_STATUSES)}")
        query = query.filter_by(status=status)

    applications = query.order_by(Application.created_at.desc()).all()
    return jsonify([a.to_dict() for a in applications])


@applications_bp.get("/applications/<application_id>")
def get_application(application_id: str):
    application = _get_application_or_404(application_id)
    return jsonify(application.to_dict())


@applications_bp.patch("/applications/<application_id>/document")
def update_application_document(application_id: str):
    application = _get_application_or_404(application_id)
    body = request.get_json(silent=True) or {}
    if "document_content" not in body:
        abort(400, description="'document_content' is required")

    application.document_content = body["document_content"]
    db.session.commit()
    logger.info("Updated document for application_id=%s", application.id)
    return jsonify(application.to_dict())


@applications_bp.post("/applications/<application_id>/regenerate")
def regenerate_application(application_id: str):
    application = _get_application_or_404(application_id)
    conversation = Conversation(
        user_id=application.user_id,
        type="application_edit",
        application_id=application.id,
    )
    db.session.add(conversation)
    db.session.commit()
    logger.info(
        "Opened application_edit conversation id=%s for application id=%s", conversation.id, application.id
    )
    return jsonify(conversation.to_dict()), 201


@applications_bp.post("/applications/<application_id>/approve")
def approve_application(application_id: str):
    application = _get_application_or_404(application_id)
    application.status = "approved"
    db.session.commit()

    publish(
        "application-approved-queue",
        {"application_id": str(application.id), "user_id": str(application.user_id)},
    )
    logger.info("Approved application_id=%s", application.id)
    return jsonify(application.to_dict())


@applications_bp.post("/applications/<application_id>/reject")
def reject_application(application_id: str):
    application = _get_application_or_404(application_id)
    application.status = "rejected"
    db.session.commit()
    logger.info("Rejected application_id=%s", application.id)
    return jsonify(application.to_dict())


@applications_bp.get("/applications/<application_id>/download")
def download_application(application_id: str):
    application = _get_application_or_404(application_id)
    if not application.document_content:
        abort(404, description="No document content available for this application yet")

    # TODO: render as PDF/Word once a document-generation library is chosen.
    # Plain-text export is used for now so the endpoint contract is usable.
    buffer = io.BytesIO(application.document_content.encode("utf-8"))
    return send_file(
        buffer,
        mimetype="text/plain",
        as_attachment=True,
        download_name=f"application-{application.id}.txt",
    )
