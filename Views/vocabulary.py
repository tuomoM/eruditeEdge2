from functools import wraps

from flask import Blueprint, current_app, jsonify, request, session

from Services.vocabulary_ai_service import vocabulary_ai_service
from Services.vocabulary_service import vocabulary_service


vocabulary_bp = Blueprint("vocabulary", __name__)


def login_required(route_function):
    @wraps(route_function)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return jsonify({"error": "Login required"}), 401
        return route_function(*args, **kwargs)

    return wrapper


@vocabulary_bp.route("/vocabulary", methods=["POST"])
@login_required
def create_vocabulary():
    data = request.get_json(silent=True) or request.form
    entry, error = vocabulary_service.create_entry(data, session["user_id"])
    if error:
        return jsonify({"error": error}), 400
    return jsonify(entry), 201


@vocabulary_bp.route("/vocabulary/generate", methods=["POST"])
@login_required
def generate_vocabulary():
    data = request.get_json(silent=True) or request.form
    entry, error = vocabulary_ai_service.generate_entry(
        data.get("word"),
        current_app.config["OPENAI_API_KEY"],
        current_app.config["OPENAI_MODEL"],
    )
    if error:
        return jsonify({"error": error}), 400

    values, error = vocabulary_service.validate_entry_data(entry)
    if error:
        return jsonify({"error": error}), 400
    return jsonify(values)


@vocabulary_bp.route("/vocabulary/<int:vocabulary_id>", methods=["GET"])
@login_required
def view_vocabulary(vocabulary_id):
    entry = vocabulary_service.get_entry(vocabulary_id)
    if not entry:
        return jsonify({"error": "Vocabulary entry was not found"}), 404
    return jsonify(entry)


@vocabulary_bp.route("/vocabulary/<int:vocabulary_id>", methods=["PUT"])
@login_required
def update_vocabulary(vocabulary_id):
    data = request.get_json(silent=True) or request.form
    entry, error = vocabulary_service.update_entry(vocabulary_id, data)
    if error:
        return jsonify({"error": error}), 400
    return jsonify(entry)
