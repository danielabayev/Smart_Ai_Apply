"""Mocked auth helper.

Auth is explicitly out of scope for the MVP (api-structure-en.md,
section 1.1): "Single fixed user, no real registration/login at this
stage." This module resolves that single user, creating it on first
access if it does not exist yet.
"""

import logging

from flask import current_app

from api.extensions import db
from api.models import User, UserPreferences

logger = logging.getLogger(__name__)


def get_current_user() -> User:
    """Fetches the platform's single mocked user, creating it if missing.

    Returns:
        User: The current (only) user row.
    """
    user = User.query.order_by(User.created_at.asc()).first()
    if user is not None:
        return user

    email = current_app.config["DEFAULT_USER_EMAIL"]
    logger.info("No user found, seeding default mocked user with email=%s", email)
    user = User(full_name="New User", email=email)
    db.session.add(user)
    db.session.flush()
    db.session.add(UserPreferences(user_id=user.id))
    db.session.commit()
    return user
