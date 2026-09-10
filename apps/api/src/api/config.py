"""Configuration for the unified API server."""

import os

from dotenv import load_dotenv

load_dotenv()


class Config:
    """Application configuration loaded from environment variables.

    Attributes:
        SQLALCHEMY_DATABASE_URI (str): PostgreSQL connection string.
        SQLALCHEMY_TRACK_MODIFICATIONS (bool): Disabled for performance.
        SQLALCHEMY_ENGINE_OPTIONS (dict): Engine-level options passed to
            SQLAlchemy. Enables `pool_pre_ping` so a pooled connection left
            stale by a DB restart/network blip is transparently replaced
            instead of raising `OperationalError` on the next request.
        DEFAULT_USER_EMAIL (str): Email used to seed/locate the single
            mocked user for this MVP (no real auth yet).
        PROFILER_AGENT_URL (str): Base URL of the Agent 1 (Profiling)
            microservice, called synchronously for each conversation turn.
        PROFILER_AGENT_TIMEOUT_SECONDS (float): Request timeout for calls to
            the profiler-agent service.
    """

    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL",
        "postgresql+psycopg://smart_ai_apply:smart_ai_apply@localhost:5432/smart_ai_apply",
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # Without pool_pre_ping, a pooled connection left stale by a DB restart/network blip
    # raises OperationalError on the next request instead of transparently reconnecting.
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}
    DEFAULT_USER_EMAIL = os.environ.get("DEFAULT_USER_EMAIL", "user@example.com")
    PROFILER_AGENT_URL = os.environ.get("PROFILER_AGENT_URL", "http://localhost:8001")
    # 120s, not the previous 60s: observed ~25-30s baseline latency from the Gemini API alone
    # on a trivial prompt, before adding a real interview system prompt + JSON schema on top.
    PROFILER_AGENT_TIMEOUT_SECONDS = float(os.environ.get("PROFILER_AGENT_TIMEOUT_SECONDS", "120"))
