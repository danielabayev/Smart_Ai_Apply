"""Helper for resetting Agent 4's per-user job scan cursor.

Per api-structure-en.md section 2.3: when a user's preferences or
building blocks change, the cursor resets to 0 so previously-rejected
jobs get re-checked against the new criteria.
"""

import logging
import uuid

from api.extensions import db
from api.models import UserJobScanCursor

logger = logging.getLogger(__name__)


def reset_job_scan_cursor(user_id: uuid.UUID) -> None:
    """Resets the user's Agent 4 scan cursor to 0."""
    cursor = db.session.get(UserJobScanCursor, user_id)
    if cursor is None:
        cursor = UserJobScanCursor(user_id=user_id, last_checked_job_id=0)
        db.session.add(cursor)
    else:
        cursor.last_checked_job_id = 0
    logger.info("Reset job scan cursor for user_id=%s", user_id)
