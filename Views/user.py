from flask import Blueprint, jsonify, request, session

from Services.user_service import user_service


user_bp = Blueprint("user", __name__)


@user_bp.route("/register", methods=["POST"])
def register():
    data = request.get_json(silent=True) or request.form
    user_id, error = user_service.register(data.get("username"), data.get("password"))
    if error:
        return jsonify({"error": error}), 400

    session["user_id"] = user_id
    session["username"] = data.get("username").strip()
    return jsonify({"id": user_id, "username": session["username"]}), 201


@user_bp.route("/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or request.form
    user_id, error = user_service.login(data.get("username"), data.get("password"))
    if error:
        return jsonify({"error": error}), 401

    session["user_id"] = user_id
    session["username"] = data.get("username").strip()
    return jsonify({"id": user_id, "username": session["username"]})


@user_bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"message": "Logged out"})
