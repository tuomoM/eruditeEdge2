from flask import Blueprint, current_app, flash, jsonify, redirect, render_template, request, session, url_for

from csrf import validate_csrf_token
from Services.google_oauth_service import google_oauth_service
from Services.user_service import user_service


user_bp = Blueprint("user", __name__)


def registration_template(username="", invite_code=""):
    return render_template(
        "register.html",
        username=username,
        invite_code=invite_code,
        google_registration_enabled=google_registration_enabled(),
    )


def google_registration_enabled():
    return bool(
        current_app.config["GOOGLE_CLIENT_ID"]
        and current_app.config["GOOGLE_CLIENT_SECRET"]
    )


def google_redirect_uri():
    return url_for("user.register_google_callback", _external=True)


def google_login_redirect_uri():
    return url_for("user.login_google_callback", _external=True)


def login_template(username=""):
    return render_template(
        "login.html",
        username=username,
        google_login_enabled=google_registration_enabled(),
    )


@user_bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        return registration_template()

    data = request.get_json(silent=True) or request.form
    csrf_error = validate_csrf_token()
    if csrf_error:
        if not request.is_json:
            flash("Invalid CSRF token")
            return registration_template(
                username=data.get("username", ""),
                invite_code=data.get("invite_code", ""),
            ), 400
        return csrf_error

    user_id, error = user_service.register(
        data.get("username"),
        data.get("password"),
        data.get("invite_code"),
    )
    if error:
        if not request.is_json:
            flash(error)
            return registration_template(
                username=data.get("username", ""),
                invite_code=data.get("invite_code", ""),
            ), 400
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


@user_bp.route("/register/google", methods=["POST"])
def register_google_start():
    data = request.get_json(silent=True) or request.form
    csrf_error = validate_csrf_token()
    if csrf_error:
        if request.is_json:
            return csrf_error
        flash("Invalid CSRF token")
        return registration_template(invite_code=data.get("invite_code", "")), 400

    invite_code = (data.get("invite_code") or "").strip()
    if not invite_code:
        error = "Invite code is required"
        if request.is_json:
            return jsonify({"error": error}), 400
        flash(error)
        return registration_template(), 400

    if not google_registration_enabled():
        error = "Google registration is not configured"
        if request.is_json:
            return jsonify({"error": error}), 400
        flash(error)
        return registration_template(invite_code=invite_code), 400

    authorization_url = google_oauth_service.create_authorization_url(
        session,
        current_app.config["GOOGLE_CLIENT_ID"],
        google_redirect_uri(),
        invite_code,
    )
    if request.is_json:
        return jsonify({"authorization_url": authorization_url})
    return redirect(authorization_url)


@user_bp.route("/register/google/callback", methods=["GET"])
def register_google_callback():
    invite_code, error = google_oauth_service.consume_registration_invite_code(
        session,
        request.args.get("state"),
    )
    if error:
        flash(error)
        return redirect("/register")

    google_user, error = google_oauth_service.fetch_user_info(
        request.args.get("code"),
        current_app.config["GOOGLE_CLIENT_ID"],
        current_app.config["GOOGLE_CLIENT_SECRET"],
        google_redirect_uri(),
    )
    if error:
        flash(error)
        return redirect("/register")

    user_id, error = user_service.register_google_user(google_user, invite_code)
    if error:
        flash(error)
        return redirect("/register")

    user = user_service.get_user(user_id)
    session["user_id"] = user_id
    session["username"] = user["username"]
    session["account_category"] = user["account_category"]
    return redirect("/vocabulary")


@user_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return login_template()

    data = request.get_json(silent=True) or request.form
    user_id, error = user_service.login(data.get("username"), data.get("password"))
    if error:
        if not request.is_json:
            flash(error)
            return login_template(data.get("username", "")), 401
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


@user_bp.route("/login/google", methods=["POST"])
def login_google_start():
    csrf_error = validate_csrf_token()
    if csrf_error:
        if request.is_json:
            return csrf_error
        flash("Invalid CSRF token")
        return login_template(), 400

    if not google_registration_enabled():
        error = "Google login is not configured"
        if request.is_json:
            return jsonify({"error": error}), 400
        flash(error)
        return login_template(), 400

    authorization_url = google_oauth_service.create_login_authorization_url(
        session,
        current_app.config["GOOGLE_CLIENT_ID"],
        google_login_redirect_uri(),
    )
    if request.is_json:
        return jsonify({"authorization_url": authorization_url})
    return redirect(authorization_url)


@user_bp.route("/login/google/callback", methods=["GET"])
def login_google_callback():
    error = google_oauth_service.validate_login_state(
        session,
        request.args.get("state"),
    )
    if error:
        flash(error)
        return redirect("/login")

    google_user, error = google_oauth_service.fetch_user_info(
        request.args.get("code"),
        current_app.config["GOOGLE_CLIENT_ID"],
        current_app.config["GOOGLE_CLIENT_SECRET"],
        google_login_redirect_uri(),
    )
    if error:
        flash(error)
        return redirect("/login")

    user_id, error = user_service.login_google_user(google_user)
    if error:
        flash(error)
        return redirect("/login")

    user = user_service.get_user(user_id)
    session["user_id"] = user_id
    session["username"] = user["username"]
    session["account_category"] = user["account_category"]
    return redirect("/vocabulary")


@user_bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    if not request.is_json:
        return redirect("/login")
    return jsonify({"message": "Logged out"})
