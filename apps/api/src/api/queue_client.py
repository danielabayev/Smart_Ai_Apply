"""Placeholder publisher for internal message queues (api-structure-en.md 2.6).

No message broker is provisioned yet. This stub logs what would be
published so the call site doesn't need to change once a real queue
(e.g. Redis Streams / RabbitMQ / SQS) is wired in.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


def publish(queue_name: str, payload: dict[str, Any]) -> None:
    """Publishes a payload to a named internal queue.

    Args:
        queue_name (str): Target queue, e.g. 'application-approved-queue'.
        payload (dict[str, Any]): Event payload.
    """
    logger.info("Publishing to queue=%s payload=%s (stub: no broker configured)", queue_name, payload)
