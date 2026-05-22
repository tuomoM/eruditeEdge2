from functools import wraps

from flask import Blueprint, current_app, flash, jsonify, redirect, render_template, request, session

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


def form_to_entry_data(form):
    synonyms = [item.strip() for item in form.get("synonyms", "").split(",")]
    examples = form.get("examples", "").splitlines()
    return {
        "word": form.get("word"),
        "definition": form.get("definition"),
        "context": form.get("context"),
        "synonyms": synonyms,
        "examples": examples,
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
        entries=entries,
        search_word=search_word,
    )


@vocabulary_bp.route("/vocabulary/new", methods=["GET", "POST"])
@page_login_required
def new_vocabulary():
    if request.method == "GET":
        return render_template("vocabulary_form.html", entry=None)

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


@vocabulary_bp.route("/vocabulary/generate/status", methods=["GET"])
@login_required
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
    return render_template("vocabulary_detail.html", entry=entry)


@vocabulary_bp.route("/vocabulary/<int:vocabulary_id>/edit", methods=["GET", "POST"])
@page_login_required
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
        ), 400
    return redirect(f"/vocabulary/{updated_entry['id']}/page")


@vocabulary_bp.route("/vocabulary/<int:vocabulary_id>", methods=["PUT"])
@login_required
def update_vocabulary(vocabulary_id):
    data = request.get_json(silent=True) or request.form
    entry, error = vocabulary_service.update_entry(vocabulary_id, data)
    if error:
        return jsonify({"error": error}), 400
    return jsonify(entry)
