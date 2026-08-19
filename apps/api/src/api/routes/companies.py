"""Company endpoints (api-structure-en.md sections 2.1 and 2.2)."""

import logging

from flask import Blueprint, abort, jsonify, request

from api.extensions import db
from api.models import Company

logger = logging.getLogger(__name__)

companies_bp = Blueprint("companies", __name__)

_COMPANY_FIELDS = {"name", "website", "status", "last_checked_at", "last_job_found_at"}


@companies_bp.post("/companies")
def create_company():
    """Create/update a discovered company. Called by Agent 2 (Discovery)."""
    body = request.get_json(silent=True) or {}
    for field in ("name", "website"):
        if field not in body:
            abort(400, description=f"'{field}' is required")

    existing = Company.query.filter_by(website=body["website"]).first()
    if existing is not None:
        for field in _COMPANY_FIELDS:
            if field in body:
                setattr(existing, field, body[field])
        db.session.commit()
        logger.info("Agent 2 updated existing company id=%s website=%s", existing.id, existing.website)
        return jsonify(existing.to_dict())

    company = Company(name=body["name"], website=body["website"])
    for field in _COMPANY_FIELDS:
        if field in body:
            setattr(company, field, body[field])
    db.session.add(company)
    db.session.commit()
    logger.info("Agent 2 created company id=%s website=%s", company.id, company.website)
    return jsonify(company.to_dict()), 201


@companies_bp.patch("/companies/<int:company_id>")
def update_company(company_id: int):
    """Update company details. Called by Agent 2 (Discovery)."""
    company = db.session.get(Company, company_id)
    if company is None:
        abort(404, description="Company not found")

    body = request.get_json(silent=True) or {}
    for field in _COMPANY_FIELDS:
        if field in body:
            setattr(company, field, body[field])
    db.session.commit()
    logger.info("Updated company id=%s", company.id)
    return jsonify(company.to_dict())


@companies_bp.get("/companies/<int:company_id>")
def get_company(company_id: int):
    """Company details. Called directly by the Frontend."""
    company = db.session.get(Company, company_id)
    if company is None:
        abort(404, description="Company not found")
    return jsonify(company.to_dict())
