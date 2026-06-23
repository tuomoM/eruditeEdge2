from functools import wraps

from flask import Blueprint, current_app, flash, jsonify, redirect, render_template, request, session

from csrf import csrf_required
from Services.ai_quota_service import ai_quota_service
from Services.user_service import ACCOUNT_CATEGORY_ADMIN, ACCOUNT_CATEGORY_TRUSTED, user_service
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


def page_login_required(route_function):
    @wraps(route_function)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return redirect("/login")
        return route_function(*args, **kwargs)

    return wrapper


def can_manage_vocabulary():
    user_id = session.get("user_id")
    if not user_id:
        return False
    user = user_service.get_user(user_id)
    if not user:
        return False
    session["username"] = user["username"]
    session["account_category"] = user["account_category"]
    return user["account_category"] in {
        ACCOUNT_CATEGORY_ADMIN,
        ACCOUNT_CATEGORY_TRUSTED,
    }


def entries_with_ownership(entries, user_id):
    current_user_id = str(user_id)
    owned_entries = []
    for entry in entries:
        owned_entry = dict(entry)
        owned_entry["owned"] = str(owned_entry.get("created_by")) == current_user_id
        owned_entry.pop("created_by", None)
        owned_entries.append(owned_entry)
    return owned_entries


def is_admin():
    user_id = session.get("user_id")
    if not user_id:
        return False
    user = user_service.get_user(user_id)
    if not user:
        return False
    session["username"] = user["username"]
    session["account_category"] = user["account_category"]
    return user["account_category"] == ACCOUNT_CATEGORY_ADMIN


def vocabulary_manager_required(route_function):
    @wraps(route_function)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return jsonify({"error": "Login required"}), 401
        if not can_manage_vocabulary():
            return jsonify({"error": "Trusted account is required"}), 403
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


def page_vocabulary_manager_required(route_function):
    @wraps(route_function)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return redirect("/login")
        if not can_manage_vocabulary():
            flash("Trusted account is required")
            return redirect("/vocabulary")
        return route_function(*args, **kwargs)

    return wrapper


def form_to_entry_data(form):
    synonyms = [item.strip() for item in form.get("synonyms", "").split(",")]
    examples = form.get("examples", "").splitlines()
    cloze_sentences = form.get("cloze_sentences", "").splitlines()
    return {
        "word": form.get("word"),
        "definition": form.get("definition"),
        "context": form.get("context"),
        "part_of_speech": form.get("part_of_speech"),
        "synonyms": synonyms,
        "examples": examples,
        "cloze_sentences": cloze_sentences,
    }


@vocabulary_bp.route("/vocabulary", methods=["GET"])
@page_login_required
def vocabulary_list():
    search_word = request.args.get("word", "").strip()
    if search_word:
        entries, error = vocabulary_service.search_by_word(search_word)
        if error:
            flash(error)
            entries = []
    else:
        entries = vocabulary_service.list_entries()
    return render_template(
        "vocabulary_list.html",
        entries=entries_with_ownership(entries, session["user_id"]),
        search_word=search_word,
    )


@vocabulary_bp.route("/vocabulary/new", methods=["GET", "POST"])
@page_vocabulary_manager_required
def new_vocabulary():
    if request.method == "GET":
        return render_template(
            "vocabulary_form.html",
            entry=None,
            prefill_word=request.args.get("word", "").strip(),
        )

    entry, error = vocabulary_service.create_entry(
        form_to_entry_data(request.form),
        session["user_id"],
    )
    if error:
        flash(error)
        return render_template(
            "vocabulary_form.html",
            entry=form_to_entry_data(request.form),
            examples_text=request.form.get("examples", ""),
        ), 400
    return redirect(f"/vocabulary/{entry['id']}/page")


@vocabulary_bp.route("/vocabulary", methods=["POST"])
@vocabulary_manager_required
def create_vocabulary():
    data = request.get_json(silent=True) or request.form
    entry, error = vocabulary_service.create_entry(data, session["user_id"])
    if error:
        return jsonify({"error": error}), 400
    return jsonify(entry), 201


@vocabulary_bp.route("/vocabulary/generate", methods=["POST"])
@vocabulary_manager_required
@csrf_required
def generate_vocabulary():
    data = request.get_json(silent=True) or request.form
    word, error = vocabulary_ai_service.validate_word(data.get("word"))
    if error:
        return jsonify({"error": error}), 400

    api_key = current_app.config["OPENAI_API_KEY"]
    if not api_key:
        return jsonify({"error": "OpenAI API key is missing"}), 400

    user = user_service.get_user(session["user_id"])
    allowed, error = ai_quota_service.record_generation_if_allowed(
        user,
        current_app.config["TRUSTED_AI_DAILY_QUOTA"],
    )
    if not allowed:
        return jsonify({"error": error}), 429

    entry, error = vocabulary_ai_service.generate_entry(
        word,
        api_key,
        current_app.config["OPENAI_MODEL"],
    )
    if error:
        ai_quota_service.refund_generation(user)
        return jsonify({"error": error}), 400

    values, error = vocabulary_service.validate_entry_data(entry)
    if error:
        ai_quota_service.refund_generation(user)
        return jsonify({"error": error}), 400
    return jsonify(values)


@vocabulary_bp.route("/vocabulary/generate/status", methods=["GET"])
@admin_required
def generate_vocabulary_status():
    api_key = current_app.config["OPENAI_API_KEY"]
    return jsonify(
        {
            "openai_api_key_present": bool(api_key),
            "openai_api_key_prefix": api_key[:7] if api_key else "",
            "openai_model": current_app.config["OPENAI_MODEL"],
        }
    )


@vocabulary_bp.route("/vocabulary/search", methods=["GET"])
@login_required
def search_vocabulary():
    entries, error = vocabulary_service.search_by_word(request.args.get("word"))
    if error:
        return jsonify({"error": error}), 400
    return jsonify(entries)


@vocabulary_bp.route("/vocabulary/<int:vocabulary_id>", methods=["GET"])
@login_required
def view_vocabulary(vocabulary_id):
    entry = vocabulary_service.get_entry(vocabulary_id)
    if not entry:
        return jsonify({"error": "Vocabulary entry was not found"}), 404
    return jsonify(entry)


@vocabulary_bp.route("/vocabulary/<int:vocabulary_id>/page", methods=["GET"])
@page_login_required
def vocabulary_page(vocabulary_id):
    entry = vocabulary_service.get_entry(vocabulary_id)
    if not entry:
        flash("Vocabulary entry was not found")
        return redirect("/vocabulary")
    return render_template(
        "vocabulary_detail.html",
        entry=entry,
        can_practice_usage=can_manage_vocabulary(),
    )


@vocabulary_bp.route("/vocabulary/<int:vocabulary_id>/practice-usage", methods=["POST"])
@vocabulary_manager_required
@csrf_required
def practice_vocabulary_usage(vocabulary_id):
    entry = vocabulary_service.get_entry(vocabulary_id)
    if not entry:
        return jsonify({"error": "Vocabulary entry was not found"}), 404

    data = request.get_json(silent=True) or request.form
    sentence = data.get("sentence")
    api_key = current_app.config["OPENAI_API_KEY"]
    if not api_key:
        return jsonify({"error": "OpenAI API key is missing"}), 400

    user = user_service.get_user(session["user_id"])
    allowed, error = ai_quota_service.record_generation_if_allowed(
        user,
        current_app.config["TRUSTED_AI_DAILY_QUOTA"],
    )
    if not allowed:
        return jsonify({"error": error}), 429

    result, error = vocabulary_ai_service.validate_usage(
        entry,
        sentence,
        api_key,
        current_app.config["OPENAI_MODEL"],
    )
    if error:
        ai_quota_service.refund_generation(user)
        return jsonify({"error": error}), 400
    return jsonify(result)


@vocabulary_bp.route("/vocabulary/<int:vocabulary_id>/edit", methods=["GET", "POST"])
@page_vocabulary_manager_required
def edit_vocabulary(vocabulary_id):
    entry = vocabulary_service.get_entry(vocabulary_id)
    if not entry:
        flash("Vocabulary entry was not found")
        return redirect("/vocabulary")

    if request.method == "GET":
        return render_template(
            "vocabulary_form.html",
            entry=entry,
            examples_text="\n".join(entry["examples"]),
            cloze_sentences_text="\n".join(entry["cloze_sentences"]),
        )

    updated_entry, error = vocabulary_service.update_entry(
        vocabulary_id,
        form_to_entry_data(request.form),
    )
    if error:
        flash(error)
        form_entry = form_to_entry_data(request.form)
        form_entry["id"] = vocabulary_id
        return render_template(
            "vocabulary_form.html",
            entry=form_entry,
            examples_text=request.form.get("examples", ""),
            cloze_sentences_text=request.form.get("cloze_sentences", ""),
        ), 400
    return redirect(f"/vocabulary/{updated_entry['id']}/page")


@vocabulary_bp.route("/vocabulary/<int:vocabulary_id>", methods=["PUT"])
@vocabulary_manager_required
def update_vocabulary(vocabulary_id):
    data = request.get_json(silent=True) or request.form
    entry, error = vocabulary_service.update_entry(vocabulary_id, data)
    if error:
        return jsonify({"error": error}), 400
    return jsonify(entry)
