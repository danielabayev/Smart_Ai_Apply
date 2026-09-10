"""Flask app for the profiler-agent microservice (agent-structure-en.md section 3)."""

import logging
import traceback

from flask import Flask, jsonify, request

from profiler_agent.config import Config
from profiler_agent.graph import run_turn
from profiler_agent.logging_utils import ColorPrefixFormatter, log_event

logger = logging.getLogger(__name__)


def create_app() -> Flask:
    """Builds the profiler-agent Flask app.

    Returns:
        Flask: The configured application instance.
    """
    handler = logging.StreamHandler()
    handler.setFormatter(ColorPrefixFormatter())
    logging.basicConfig(level=logging.WARNING, handlers=[handler])
    logging.getLogger("profiler_agent").setLevel(logging.DEBUG)

    app = Flask(__name__)

    @app.get("/health")
    def health() -> tuple[dict, int]:
        return {"status": "ok", "service": "profiler-agent"}, 200

    @app.post("/reply")
    def reply() -> tuple[dict, int]:
        body = request.get_json(silent=True) or {}
        try:
            result = run_turn(body)
        except Exception as exc:  # noqa: BLE001 - deliberate: log, then fail loudly.
            log_event(
                level="ERROR",
                session_id=body.get("conversation_id"),
                user_id=body.get("user_id"),
                message_id=None,
                role_id=None,
                event_category="ERROR",
                details={
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                    "traceback": traceback.format_exc(),
                    "conversation_type": body.get("conversation_type"),
                    "building_block_id": body.get("building_block_id"),
                    "application_id": body.get("application_id"),
                },
            )
            return jsonify({"error": str(exc)}), 500
        return jsonify(result), 200

    return app


def main() -> None:
    """Entry point for `uv run profiler-agent`."""
    app = create_app()
    app.run(host="0.0.0.0", port=Config.PORT)


if __name__ == "__main__":
    main()
