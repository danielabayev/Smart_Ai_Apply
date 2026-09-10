"""Helper for resetting Agent 4's per-user job scan cursor.

Per api-structure-en.md section 2.3: when a user's preferences or
building blocks change, the cursor resets to 0 so previously-rejected
jobs get re-checked against the new criteria.
"""

import logging
import uuid

from sqlalchemy.dialects.postgresql import insert as pg_insert

from api.extensions import db
from api.models import UserJobScanCursor

logger = logging.getLogger(__name__)


def reset_job_scan_cursor(user_id: uuid.UUID) -> None:
    """Resets the user's Agent 4 scan cursor to 0.

    Uses an atomic INSERT ... ON CONFLICT DO UPDATE (upsert) instead of a
    read-then-write, since two overlapping requests for the same user could
    otherwise both see "no cursor row" and race to insert one.
    """
    stmt = pg_insert(UserJobScanCursor).values(user_id=user_id, last_checked_job_id=0)
    stmt = stmt.on_conflict_do_update(
        index_elements=["user_id"],
        set_={"last_checked_job_id": 0},
    )
    db.session.execute(stmt)
    logger.info("Reset job scan cursor for user_id=%s", user_id)
