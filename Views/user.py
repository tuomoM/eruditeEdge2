from flask import Blueprint, flash, jsonify, redirect, render_template, request, session

from Services.user_service import user_service


user_bp = Blueprint("user", __name__)


@user_bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        return render_template("register.html")

    data = request.get_json(silent=True) or request.form
    user_id, error = user_service.register(data.get("username"), data.get("password"))
    if error:
        if not request.is_json:
            flash(error)
            return render_template("register.html", username=data.get("username", "")), 400
        return jsonify({"error": error}), 400

    session["user_id"] = user_id
    session["username"] = data.get("username").strip()
    user = user_service.get_user(user_id)
    session["account_category"] = user["account_category"]
    if not request.is_json:
        return redirect("/vocabulary")
    return jsonify(
        {
            "id": user_id,
            "username": session["username"],
            "account_category": session["account_category"],
        }
    ), 201


@user_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("login.html")

    data = request.get_json(silent=True) or request.form
    user_id, error = user_service.login(data.get("username"), data.get("password"))
    if error:
        if not request.is_json:
            flash(error)
            return render_template("login.html", username=data.get("username", "")), 401
        return jsonify({"error": error}), 401

    session["user_id"] = user_id
    session["username"] = data.get("username").strip()
    user = user_service.get_user(user_id)
    session["account_category"] = user["account_category"]
    if not request.is_json:
        return redirect("/vocabulary")
    return jsonify(
        {
            "id": user_id,
            "username": session["username"],
            "account_category": session["account_category"],
        }
    )


@user_bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    if not request.is_json:
        return redirect("/login")
    return jsonify({"message": "Logged out"})
