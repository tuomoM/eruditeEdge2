import logging

from flask import Flask, redirect, session

import config
import db
from csrf import get_csrf_token
from cli import register_cli_commands
from Views.admin import admin_bp
from Views.training import training_bp
from Views.user import user_bp
from Views.vocabulary import vocabulary_bp


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.from_object(config)
    if test_config:
        app.config.update(test_config)
    logging.basicConfig(level=logging.INFO)

    app.teardown_appcontext(db.close_connection)
    app.register_blueprint(admin_bp)
    app.register_blueprint(user_bp)
    app.register_blueprint(vocabulary_bp)
    app.register_blueprint(training_bp)
    register_cli_commands(app)

    @app.context_processor
    def inject_csrf_token():
        return {"csrf_token": get_csrf_token}

    @app.route("/")
    def index():
        if "user_id" in session:
            return redirect("/vocabulary")
        return redirect("/login")

    return app


app = create_app()
