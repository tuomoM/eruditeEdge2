from functools import wraps

from flask import Blueprint, current_app, flash, jsonify, redirect, render_template, request, session

from csrf import validate_csrf_token
from Services.ai_quota_service import ai_quota_service
from Services.invite_code_service import invite_code_service
from Services.user_service import ACCOUNT_CATEGORY_ADMIN, user_service
from Services.vocabulary_service import vocabulary_service


admin_bp = Blueprint("admin", __name__)


def current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None
    user = user_service.get_user(user_id)
    if user:
        session["username"] = user["username"]
        session["account_category"] = user["account_category"]
    return user


def is_admin():
    user = current_user()
    return bool(user and user["account_category"] == ACCOUNT_CATEGORY_ADMIN)


def csrf_required(route_function):
    @wraps(route_function)
    def wrapper(*args, **kwargs):
        error = validate_csrf_token()
        if error:
            if request.is_json:
                return error
            flash(error)
            return redirect("/admin")
        return route_function(*args, **kwargs)

    return wrapper


def admin_required(route_function):
    @wraps(route_function)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return jsonify({"error": "Login required"}), 401
        if not is_admin():
            return jsonify({"error": "Admin account is required"}), 403
        return route_function(*args, **kwargs)

    return wrapper


def page_admin_required(route_function):
    @wraps(route_function)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return redirect("/login")
        if not is_admin():
            flash("Admin account is required")
            return redirect("/vocabulary")
        return route_function(*args, **kwargs)

    return wrapper


@admin_bp.route("/admin", methods=["GET"])
@page_admin_required
def admin_page():
    acting_user = current_user()
    users, error = user_service.list_users(session["user_id"])
    if error:
        flash(error)
        return redirect("/vocabulary")
    invite_codes, error = invite_code_service.list_invite_codes(acting_user)
    if error:
        flash(error)
        return redirect("/vocabulary")
    usage_by_user = ai_quota_service.usage_by_user()
    trusted_quota = current_app.config["TRUSTED_AI_DAILY_QUOTA"]
    for user in users:
        user["ai_generation_count"] = usage_by_user.get(user["id"], 0)
        user["ai_generation_quota"] = (
            None if user["account_category"] == ACCOUNT_CATEGORY_ADMIN else trusted_quota
        )
    return render_template("admin.html", users=users, invite_codes=invite_codes)


@admin_bp.route("/admin/users/<int:user_id>/category", methods=["POST"])
@admin_required
@csrf_required
def update_user_category(user_id):
    account_category = request.form.get("account_category")
    if request.is_json:
        data = request.get_json(silent=True) or {}
        account_category = data.get("account_category")

    user, error = user_service.update_account_category(
        session["user_id"],
        user_id,
        account_category,
    )
    if error:
        if request.is_json:
            return jsonify({"error": error}), 400
        flash(error)
        return redirect("/admin")

    if request.is_json:
        return jsonify(
            {
                "id": user["id"],
                "username": user["username"],
                "account_category": user["account_category"],
            }
        )
    flash(f"Updated {user['username']} to {user['account_category']}.")
    return redirect("/admin")


@admin_bp.route("/admin/users/<int:user_id>/vocabs/delete", methods=["POST"])
@admin_required
@csrf_required
def delete_user_vocabs(user_id):
    target_user = user_service.get_user(user_id)
    if not target_user:
        if request.is_json:
            return jsonify({"error": "User was not found"}), 404
        flash("User was not found")
        return redirect("/admin")

    deleted_count = vocabulary_service.delete_entries_by_user(user_id)
    if request.is_json:
        return jsonify(
            {
                "user_id": user_id,
                "deleted_vocabulary_count": deleted_count,
            }
        )
    flash(f"Removed {deleted_count} vocabulary entries by {target_user['username']}.")
    return redirect("/admin")


@admin_bp.route("/admin/users/<int:user_id>/ai-quota/reset", methods=["POST"])
@admin_required
@csrf_required
def reset_user_ai_quota(user_id):
    target_user = user_service.get_user(user_id)
    if not target_user:
        if request.is_json:
            return jsonify({"error": "User was not found"}), 404
        flash("User was not found")
        return redirect("/admin")

    ai_quota_service.reset_user_usage(user_id)
    if request.is_json:
        return jsonify(
            {
                "user_id": user_id,
                "ai_generation_count": 0,
            }
        )
    flash(f"Reset AI quota for {target_user['username']}.")
    return redirect("/admin")


@admin_bp.route("/admin/invite-codes", methods=["POST"])
@admin_required
@csrf_required
def create_invite_code():
    invite_code, error = invite_code_service.create_invite_code(current_user())
    if error:
        if request.is_json:
            return jsonify({"error": error}), 403
        flash(error)
        return redirect("/admin")

    if request.is_json:
        return jsonify(invite_code), 201
    flash(f"Created invite code {invite_code['code']}.")
    return redirect("/admin")
