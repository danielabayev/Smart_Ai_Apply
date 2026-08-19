"""Configuration for the unified API server."""

import os


class Config:
    """Application configuration loaded from environment variables.

    Attributes:
        SQLALCHEMY_DATABASE_URI (str): PostgreSQL connection string.
        SQLALCHEMY_TRACK_MODIFICATIONS (bool): Disabled for performance.
        DEFAULT_USER_EMAIL (str): Email used to seed/locate the single
            mocked user for this MVP (no real auth yet).
    """

    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL",
        "postgresql+psycopg://smart_ai_apply:smart_ai_apply@localhost:5432/smart_ai_apply",
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    DEFAULT_USER_EMAIL = os.environ.get("DEFAULT_USER_EMAIL", "user@example.com")
