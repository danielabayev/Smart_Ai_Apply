"""Flask application factory for the unified API server."""

import logging

from flask import Flask

from api.config import Config
from api.extensions import db
from api.routes.applications import applications_bp
from api.routes.building_blocks import building_blocks_bp
from api.routes.companies import companies_bp
from api.routes.conversations import conversations_bp
from api.routes.internal import internal_bp
from api.routes.jobs import jobs_bp
from api.routes.profile import profile_bp

API_PREFIX = "/api/v1"


def create_app(config_object: type[Config] = Config) -> Flask:
    """Builds and configures the API server Flask app.

    Args:
        config_object (type[Config]): Configuration class to load.

    Returns:
        Flask: The configured application instance.
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )

    app = Flask(__name__)
    app.config.from_object(config_object)

    db.init_app(app)

    app.register_blueprint(profile_bp, url_prefix=API_PREFIX)
    app.register_blueprint(conversations_bp, url_prefix=API_PREFIX)
    app.register_blueprint(building_blocks_bp, url_prefix=API_PREFIX)
    app.register_blueprint(applications_bp, url_prefix=API_PREFIX)
    app.register_blueprint(internal_bp, url_prefix=API_PREFIX)
    app.register_blueprint(companies_bp, url_prefix=API_PREFIX)
    app.register_blueprint(jobs_bp, url_prefix=API_PREFIX)

    @app.get("/health")
    def health() -> tuple[dict, int]:
        return {"status": "ok", "service": "api"}, 200

    return app
