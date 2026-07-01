import logging

from flask import Flask, redirect, render_template, session

import config
import db
from csrf import get_csrf_token
from cli import register_cli_commands
from Services.vocabulary_domains import MAX_VOCABULARY_DOMAINS, VOCABULARY_DOMAINS
from Views.admin import admin_bp
from Views.training import training_bp
from Views.user import user_bp
from Views.vocabulary import vocabulary_bp


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.from_object(config)
    if test_config:
        app.config.update(test_config)
    _configure_session_security(app)
    _validate_secret_key(app)
    logging.basicConfig(level=logging.INFO)

    app.teardown_appcontext(db.close_connection)
    app.register_blueprint(admin_bp)
    app.register_blueprint(user_bp)
    app.register_blueprint(vocabulary_bp)
    app.register_blueprint(training_bp)
    register_cli_commands(app)

    @app.context_processor
    def inject_csrf_token():
        return {
            "available_domains": VOCABULARY_DOMAINS,
            "csrf_token": get_csrf_token,
            "max_domains": MAX_VOCABULARY_DOMAINS,
        }

    @app.route("/")
    def index():
        if "user_id" in session:
            return redirect("/vocabulary")
        return render_template("landing.html")

    return app


def _configure_session_security(app):
    app.config.setdefault("SESSION_COOKIE_HTTPONLY", True)
    app.config.setdefault("SESSION_COOKIE_SAMESITE", "Lax")
    app_env = app.config.get("APP_ENV", "development")
    if not app.config.get("TESTING") and app_env not in {"development", "dev", "local"}:
        app.config["SESSION_COOKIE_SECURE"] = True


def _validate_secret_key(app):
    if app.config.get("TESTING"):
        return

    app_env = app.config.get("APP_ENV", "development")
    if app_env in {"development", "dev", "local", "testing", "test"}:
        return

    secret_key = app.config.get("SECRET_KEY")
    if not secret_key or secret_key == "dev-secret-key":
        raise RuntimeError("SECRET_KEY must be set for production environments")


app = create_app()
