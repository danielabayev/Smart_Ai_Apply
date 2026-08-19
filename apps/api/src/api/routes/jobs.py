"""Job endpoints (api-structure-en.md sections 2.1 and 2.2)."""

import logging

from flask import Blueprint, abort, jsonify, request

from api.extensions import db
from api.models import Job

logger = logging.getLogger(__name__)

jobs_bp = Blueprint("jobs", __name__)

_JOB_FIELDS = {
    "title",
    "description",
    "requirements",
    "source_url",
    "salary_min",
    "salary_max",
    "salary_currency",
    "employment_type",
    "work_arrangement",
    "location",
}


@jobs_bp.post("/jobs")
def create_job():
    """Create an extracted job (auto-assigned sequential id). Called by Agent 3."""
    body = request.get_json(silent=True) or {}
    for field in ("company_id", "title", "description", "source_url"):
        if field not in body:
            abort(400, description=f"'{field}' is required")

    job = Job(
        company_id=body["company_id"],
        title=body["title"],
        description=body["description"],
        source_url=body["source_url"],
    )
    for field in _JOB_FIELDS:
        if field in body:
            setattr(job, field, body[field])
    db.session.add(job)
    db.session.commit()
    logger.info("Agent 3 created job id=%s company_id=%s", job.id, job.company_id)
    return jsonify(job.to_dict()), 201


@jobs_bp.patch("/jobs/<int:job_id>")
def update_job(job_id: int):
    """Update job details. Called by Agent 3 (Extractor)."""
    job = db.session.get(Job, job_id)
    if job is None:
        abort(404, description="Job not found")

    body = request.get_json(silent=True) or {}
    for field in _JOB_FIELDS:
        if field in body:
            setattr(job, field, body[field])
    db.session.commit()
    logger.info("Updated job id=%s", job.id)
    return jsonify(job.to_dict())


@jobs_bp.get("/jobs")
def list_jobs():
    """List jobs (search/filter). Called directly by the Frontend."""
    query = Job.query

    company_id = request.args.get("company_id", type=int)
    if company_id is not None:
        query = query.filter_by(company_id=company_id)

    title = request.args.get("title")
    if title:
        query = query.filter(Job.title.ilike(f"%{title}%"))

    location = request.args.get("location")
    if location:
        query = query.filter(Job.location.ilike(f"%{location}%"))

    work_arrangement = request.args.get("work_arrangement")
    if work_arrangement:
        query = query.filter_by(work_arrangement=work_arrangement)

    employment_type = request.args.get("employment_type")
    if employment_type:
        query = query.filter_by(employment_type=employment_type)

    jobs = query.order_by(Job.discovered_at.desc()).limit(100).all()
    return jsonify([j.to_dict() for j in jobs])


@jobs_bp.get("/jobs/<int:job_id>")
def get_job(job_id: int):
    """Specific job details. Called directly by the Frontend."""
    job = db.session.get(Job, job_id)
    if job is None:
        abort(404, description="Job not found")
    return jsonify(job.to_dict())
