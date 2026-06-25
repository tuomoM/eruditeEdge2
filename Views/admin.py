from functools import wraps
from datetime import datetime, timedelta, timezone

from flask import Blueprint, current_app, flash, jsonify, redirect, render_template, request, session

from csrf import validate_csrf_token
from Services.access_request_service import access_request_service
from Services.ai_quota_service import ai_quota_service
from Services.invite_code_service import invite_code_service
from Services.security_report_service import security_report_service
from Services.user_service import ACCOUNT_CATEGORY_ADMIN, user_service
from Services.vocabulary_ai_service import vocabulary_ai_service
from Services.vocabulary_domains import MAX_VOCABULARY_DOMAINS, VOCABULARY_DOMAINS
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
    access_requests, error = access_request_service.list_access_requests(acting_user)
    if error:
        flash(error)
        return redirect("/vocabulary")
    security_report = security_report_service.read_report(
        current_app.config["SECURITY_REPORT_PATH"],
    )
    usage_by_user = ai_quota_service.usage_by_user()
    trusted_quota = current_app.config["TRUSTED_AI_DAILY_QUOTA"]
    for user in users:
        user["ai_generation_count"] = usage_by_user.get(user["id"], 0)
        user["ai_generation_quota"] = (
            None if user["account_category"] == ACCOUNT_CATEGORY_ADMIN else trusted_quota
        )
        user["created_at_label"] = format_admin_timestamp(user.get("created_at"))
    for invite_code in invite_codes:
        invite_code["expires_at_label"] = format_admin_timestamp(invite_code.get("expires_at"))
    for access_request in access_requests:
        access_request["created_at_label"] = format_admin_timestamp(access_request.get("created_at"))
    security_report["last_run_label"] = format_admin_timestamp(security_report.get("last_run_at"))
    admin_summary, error = build_admin_summary(
        session["user_id"],
        users,
        invite_codes,
        access_requests,
        security_report,
    )
    if error:
        flash(error)
        return redirect("/vocabulary")
    return render_template(
        "admin.html",
        users=users,
        admin_summary=admin_summary,
        invite_codes=invite_codes,
        access_requests=access_requests,
        security_report=security_report,
    )


@admin_bp.route("/admin/vocabulary-maintenance", methods=["GET"])
@page_admin_required
def vocabulary_maintenance_page():
    selected_view = request.args.get("view", "missing")
    if selected_view == "all":
        entries = vocabulary_service.list_entries()
    else:
        selected_view = "missing"
        entries = vocabulary_service.list_cloze_maintenance_entries()

    return render_template(
        "admin_vocabulary_maintenance.html",
        entries=entries,
        selected_view=selected_view,
        available_domains=VOCABULARY_DOMAINS,
        max_domains=MAX_VOCABULARY_DOMAINS,
    )


@admin_bp.route("/admin/vocabulary/<int:vocabulary_id>/cloze-data", methods=["POST"])
@admin_required
@csrf_required
def update_vocabulary_cloze_data(vocabulary_id):
    if request.is_json:
        data = request.get_json(silent=True) or {}
    else:
        data = {
            "part_of_speech": request.form.get("part_of_speech"),
            "domains": request.form.getlist("domains"),
            "cloze_sentences": request.form.get("cloze_sentences", "").splitlines(),
        }

    entry, error = vocabulary_service.update_cloze_data(vocabulary_id, data)
    if error:
        if request.is_json:
            return jsonify({"error": error}), 400
        flash(error)
        return redirect(_vocabulary_maintenance_url())

    if request.is_json:
        return jsonify(entry)
    flash(f"Updated part of speech, domains, and cloze data for {entry['word']}.")
    return redirect(_vocabulary_maintenance_url())


@admin_bp.route("/admin/vocabulary/<int:vocabulary_id>/generate-cloze-data", methods=["POST"])
@admin_required
@csrf_required
def generate_vocabulary_cloze_data(vocabulary_id):
    entry = vocabulary_service.get_entry(vocabulary_id)
    if not entry:
        if request.is_json:
            return jsonify({"error": "Vocabulary entry was not found"}), 404
        flash("Vocabulary entry was not found")
        return redirect(_vocabulary_maintenance_url())

    api_key = current_app.config["OPENAI_API_KEY"]
    if not api_key:
        if request.is_json:
            return jsonify({"error": "OpenAI API key is missing"}), 400
        flash("OpenAI API key is missing")
        return redirect(_vocabulary_maintenance_url())

    generated_data, error = vocabulary_ai_service.generate_cloze_data(
        entry,
        api_key,
        current_app.config["OPENAI_MODEL"],
    )
    if error:
        if request.is_json:
            return jsonify({"error": error}), 400
        flash(error)
        return redirect(_vocabulary_maintenance_url())

    update_data = {
        "part_of_speech": (
            generated_data["part_of_speech"]
            if entry["part_of_speech"] == "other"
            else entry["part_of_speech"]
        ),
        "domains": entry["domains"] or generated_data.get("domains", []),
        "cloze_sentences": entry["cloze_sentences"] or generated_data["cloze_sentences"],
    }
    updated_entry, error = vocabulary_service.update_cloze_data(vocabulary_id, update_data)
    if error:
        if request.is_json:
            return jsonify({"error": error}), 400
        flash(error)
        return redirect(_vocabulary_maintenance_url())

    if request.is_json:
        return jsonify(updated_entry)
    flash(f"Generated cloze data for {updated_entry['word']}.")
    return redirect(_vocabulary_maintenance_url())


def _vocabulary_maintenance_url():
    if request.args.get("view") == "all":
        return "/admin/vocabulary-maintenance?view=all"
    return "/admin/vocabulary-maintenance"


def build_admin_summary(acting_user_id, users, invite_codes, access_requests, security_report):
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = now - timedelta(days=7)

    today_cutoff = format_sqlite_timestamp(today_start)
    week_cutoff = format_sqlite_timestamp(week_start)

    users_today, error = user_service.count_users_created_since(acting_user_id, today_cutoff)
    if error:
        return None, error
    users_week, error = user_service.count_users_created_since(acting_user_id, week_cutoff)
    if error:
        return None, error

    return {
        "users_today": users_today,
        "users_week": users_week,
        "vocab_today": vocabulary_service.count_entries_created_since(today_cutoff),
        "vocab_week": vocabulary_service.count_entries_created_since(week_cutoff),
        "pending_access_requests": len(access_requests),
        "active_invite_codes": len(invite_codes),
        "vulnerability_count": security_report.get("vulnerability_count", 0),
        "quota_pressure_count": count_users_at_ai_quota(users),
    }, None


def format_sqlite_timestamp(value):
    return value.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def format_admin_timestamp(value):
    if not value:
        return ""
    try:
        if isinstance(value, str):
            normalized_value = value.replace("Z", "+00:00")
            if "T" in normalized_value:
                parsed_value = datetime.fromisoformat(normalized_value)
            else:
                parsed_value = datetime.strptime(normalized_value, "%Y-%m-%d %H:%M:%S")
                parsed_value = parsed_value.replace(tzinfo=timezone.utc)
        else:
            parsed_value = value
    except (TypeError, ValueError):
        return value
    return parsed_value.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def count_users_at_ai_quota(users):
    count = 0
    for user in users:
        quota = user.get("ai_generation_quota")
        if quota is not None and user.get("ai_generation_count", 0) >= quota:
            count += 1
    return count


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


@admin_bp.route("/admin/users/<int:user_id>/vocabs/delete/confirm", methods=["GET"])
@page_admin_required
def confirm_delete_user_vocabs(user_id):
    target_user = user_service.get_user(user_id)
    if not target_user:
        flash("User was not found")
        return redirect("/admin")
    if target_user["account_category"] == ACCOUNT_CATEGORY_ADMIN:
        flash("Admin vocabulary entries cannot be removed here")
        return redirect("/admin")

    users, error = user_service.list_users(session["user_id"])
    if error:
        flash(error)
        return redirect("/admin")
    vocabulary_count = next(
        (
            user["vocabulary_count"]
            for user in users
            if user["id"] == user_id
        ),
        0,
    )
    return render_template(
        "admin_confirm_vocab_delete.html",
        target_user=target_user,
        vocabulary_count=vocabulary_count,
    )


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
    if target_user["account_category"] == ACCOUNT_CATEGORY_ADMIN:
        if request.is_json:
            return jsonify({"error": "Admin vocabulary entries cannot be removed here"}), 400
        flash("Admin vocabulary entries cannot be removed here")
        return redirect("/admin")

    if request.is_json:
        data = request.get_json(silent=True) or {}
        confirmed = data.get("confirmed") is True
    else:
        confirmed = request.form.get("confirmed") == "yes"
    if not confirmed:
        if request.is_json:
            return jsonify({"error": "Vocabulary deletion must be confirmed"}), 400
        flash("Vocabulary deletion was not confirmed")
        return redirect(f"/admin/users/{user_id}/vocabs/delete/confirm")

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


@admin_bp.route("/admin/security-report/run", methods=["POST"])
@admin_required
@csrf_required
def run_security_report():
    generated, error = security_report_service.generate_report(
        current_app.config["SECURITY_REPORT_PATH"],
        current_app.root_path,
    )
    if error:
        if request.is_json:
            return jsonify({"error": error}), 500
        flash(error)
        return redirect("/admin")

    if request.is_json:
        return jsonify({"generated": generated})
    flash("Generated dependency security report.")
    return redirect("/admin")


@admin_bp.route("/admin/access-requests/<int:access_request_id>/delete", methods=["POST"])
@admin_required
@csrf_required
def delete_access_request(access_request_id):
    deleted, error = access_request_service.delete_access_request(
        current_user(),
        access_request_id,
    )
    if error:
        status_code = 404 if error == "Invite code request was not found" else 403
        if request.is_json:
            return jsonify({"error": error}), status_code
        flash(error)
        return redirect("/admin")

    if request.is_json:
        return jsonify({"id": access_request_id, "deleted": deleted})
    flash("Deleted invite code request.")
    return redirect("/admin")
