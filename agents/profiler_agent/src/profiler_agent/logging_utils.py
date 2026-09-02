"""Structured DEBUG-level event logging (Initial_prompt.txt, Phase 3.6).

Every step of the interview/generation pipeline calls `log_event` before any
outgoing side effect (returning a reply, or handing back building block
mutations) - there is no separate log DB/service, everything goes to stdout
via the standard `logging` module.
"""

import json
import logging
from typing import Any

logger = logging.getLogger("profiler_agent.trace")
logger.setLevel(logging.DEBUG)

# Maps standard level names ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL",
# ...) to their numeric `logging` values, so `level` drives the actual
# severity the record is emitted at rather than a binary error/debug choice.
_LEVEL_NAME_TO_VALUE: dict[str, int] = logging.getLevelNamesMapping()

# Suggested values for `event_category` on normal (non-error) turns. Not an
# enforced enum - error paths use "ERROR" instead, and future categories can
# be added without a schema change.
INPUT_PROCESSING = "INPUT_PROCESSING"
FACT_EXTRACTION = "FACT_EXTRACTION"
ANGLE_SYNTHESIS = "ANGLE_SYNTHESIS"
USER_EDIT = "USER_EDIT"
DB_PAYLOAD_PREP = "DB_PAYLOAD_PREP"
DB_RESPONSE_EVAL = "DB_RESPONSE_EVAL"


def log_event(
    level: str,
    session_id: str | None,
    user_id: str | None,
    message_id: int | None,
    role_id: str | None,
    event_category: str,
    details: dict[str, Any],
) -> None:
    """Emits one structured trace record to stdout.

    Args:
        level (str): Log severity name recognized by the standard `logging`
            module ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL", ...),
            case-insensitive. Unrecognized names fall back to DEBUG.
        session_id (str | None): Conversation trace id (`conversation_id`).
        user_id (str | None): Target user identifier, if known.
        message_id (int | None): Monotonically increasing turn counter.
        role_id (str | None): Active role/company identifier, or None -
            the platform has no concrete "active role" concept yet, so this
            is always None for now.
        event_category (str): One of the categories above, or "ERROR".
        details (dict[str, Any]): Structured metadata - raw input summary,
            extracted entities/metrics, decision reasoning, triggered actions.

    Raises:
        None.
    """
    record = {
        "level": level,
        "session_id": session_id,
        "user_id": user_id,
        "message_id": message_id,
        "role_id": role_id,
        "event_category": event_category,
        "details": details,
    }
    level_value = _LEVEL_NAME_TO_VALUE.get(level.upper(), logging.DEBUG)
    logger.log(level_value, json.dumps(record, default=str))
