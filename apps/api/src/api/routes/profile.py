"""Profile & preferences endpoints (api-structure-en.md section 1.2)."""

import logging

from flask import Blueprint, jsonify, request

from api.current_user import get_current_user
from api.extensions import db
from api.job_scan_cursor import reset_job_scan_cursor
from api.models import UserPreferences

logger = logging.getLogger(__name__)

profile_bp = Blueprint("profile", __name__)

_USER_PATCHABLE_FIELDS = {"full_name", "phone_number", "linkedin_url", "github_url"}
_PREFERENCES_FIELDS = {
    "match_threshold",
    "min_salary",
    "salary_currency",
    "include_jobs_without_salary",
    "location",
    "work_arrangement",
    "employment_types",
}


@profile_bp.get("/users/me")
def get_me():
    user = get_current_user()
    return jsonify(user.to_dict())


@profile_bp.patch("/users/me")
def update_me():
    user = get_current_user()
    body = request.get_json(silent=True) or {}
    for field in _USER_PATCHABLE_FIELDS:
        if field in body:
            setattr(user, field, body[field])
    db.session.commit()
    logger.info("Updated user profile user_id=%s", user.id)
    return jsonify(user.to_dict())


@profile_bp.get("/users/me/preferences")
def get_preferences():
    user = get_current_user()
    if user.preferences is None:
        user.preferences = UserPreferences(user_id=user.id)
        db.session.commit()
    return jsonify(user.preferences.to_dict())


@profile_bp.put("/users/me/preferences")
def update_preferences():
    user = get_current_user()
    body = request.get_json(silent=True) or {}

    prefs = user.preferences
    if prefs is None:
        prefs = UserPreferences(user_id=user.id)
        db.session.add(prefs)

    for field in _PREFERENCES_FIELDS:
        if field in body:
            setattr(prefs, field, body[field])

    reset_job_scan_cursor(user.id)
    db.session.commit()
    logger.info("Updated preferences for user_id=%s", user.id)
    return jsonify(prefs.to_dict())
