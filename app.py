from flask import Flask, jsonify, session

import config
import db
from Views.user import user_bp
from Views.vocabulary import vocabulary_bp


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.from_object(config)
    if test_config:
        app.config.update(test_config)

    app.teardown_appcontext(db.close_connection)
    app.register_blueprint(user_bp)
    app.register_blueprint(vocabulary_bp)

    @app.route("/")
    def index():
        if "user_id" in session:
            return jsonify({"message": "Logged in", "username": session["username"]})
        return jsonify({"message": "Not logged in"})

    return app


app = create_app()
