import os

from flask import (
    Blueprint,
    after_this_request,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    session,
)

from Services.anki_export_service import anki_export_service
from Services.training_service import training_service
from Services.user_service import ACCOUNT_CATEGORY_ADMIN, user_service
from Services.vocabulary_service import vocabulary_service
from Views.vocabulary import entries_with_ownership, login_required, page_login_required


training_bp = Blueprint("training", __name__)


@training_bp.route("/training/select", methods=["GET"])
@page_login_required
def select_training_vocabs():
    _is_admin()
    return render_template(
        "training_select.html",
        entries=entries_with_ownership(vocabulary_service.list_entries(), session["user_id"]),
        selected_vocabulary_ids=set(
            training_service.get_latest_training_vocabulary_ids(session["user_id"])
        ),
    )


def _is_admin():
    user = user_service.get_user(session.get("user_id"))
    if user:
        session["account_category"] = user["account_category"]
    return bool(user and user["account_category"] == ACCOUNT_CATEGORY_ADMIN)


@training_bp.route("/training", methods=["POST"])
@login_required
def create_training():
    if request.is_json:
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify({"error": "Invalid request"}), 400
        vocabulary_ids = data.get("vocabulary_ids")
        training_type = data.get("training_type", "definition")
    else:
        vocabulary_ids = request.form.getlist("vocabulary_ids")
        training_type = request.form.get("training_type", "definition")

    training_session, error = training_service.create_training_session(
        session["user_id"],
        vocabulary_ids,
        training_type,
    )
    if error:
        if request.is_json:
            return jsonify({"error": error}), 400
        return render_template(
            "training_select.html",
            entries=entries_with_ownership(vocabulary_service.list_entries(), session["user_id"]),
            error=error,
            selected_vocabulary_ids={
                int(vocabulary_id)
                for vocabulary_id in vocabulary_ids
                if isinstance(vocabulary_id, str) and vocabulary_id.isdigit()
            },
            selected_training_type=training_type,
        ), 400

    if request.is_json:
        return jsonify(training_service.get_training_quiz(training_session["id"], session["user_id"])), 201
    return redirect(f"/training/{training_session['id']}")


@training_bp.route("/training/export-anki", methods=["POST"])
@login_required
def export_training_anki():
    if not _is_admin():
        return jsonify({"error": "Admin account is required"}), 403

    if request.is_json:
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify({"error": "Invalid request"}), 400
        vocabulary_ids = data.get("vocabulary_ids")
    else:
        vocabulary_ids = request.form.getlist("vocabulary_ids")

    entries, error = training_service.get_selected_vocabulary_entries(vocabulary_ids)
    if error:
        return jsonify({"error": error}), 400

    try:
        package_path = anki_export_service.export_vocabulary_entries_to_file(entries)
    except RuntimeError as error:
        return jsonify({"error": str(error)}), 500

    response = send_file(
        package_path,
        as_attachment=True,
        download_name="erudite-edge-vocabulary.apkg",
        mimetype="application/zip",
        max_age=0,
    )
    response.direct_passthrough = False

    @after_this_request
    def remove_package_file(response):
        try:
            os.unlink(package_path)
        except FileNotFoundError:
            pass
        return response

    return response


@training_bp.route("/training/<int:training_session_id>", methods=["GET"])
@page_login_required
def view_training(training_session_id):
    training_session = training_service.get_training_session(
        training_session_id,
        session["user_id"],
    )
    if not training_session:
        return redirect("/training/select")
    if training_session["submitted_at"] is not None:
        result = training_service.get_training_result(
            training_session_id,
            session["user_id"],
        )
        return render_template("training_result.html", result=result)
    return render_template(
        "training_detail.html",
        training=training_service.get_training_quiz(training_session_id, session["user_id"]),
    )


@training_bp.route("/training/<int:training_session_id>/submit", methods=["POST"])
@login_required
def submit_training(training_session_id):
    if request.is_json:
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify({"error": "Invalid request"}), 400
        answers = data.get("answers", {})
    else:
        answers = {
            key.removeprefix("answer_"): value
            for key, value in request.form.items()
            if key.startswith("answer_")
        }

    result, error = training_service.submit_training_session(
        training_session_id,
        session["user_id"],
        answers,
    )
    if error:
        if request.is_json:
            status_code = 404 if error == "Training session was not found" else 400
            return jsonify({"error": error}), status_code
        return redirect("/training/select")

    if request.is_json:
        return jsonify(result)
    return render_template("training_result.html", result=result)
