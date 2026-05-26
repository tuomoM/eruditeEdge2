from flask import Blueprint, jsonify, redirect, render_template, request, session

from Services.training_service import training_service
from Services.vocabulary_service import vocabulary_service
from Views.vocabulary import login_required, page_login_required


training_bp = Blueprint("training", __name__)


@training_bp.route("/training/select", methods=["GET"])
@page_login_required
def select_training_vocabs():
    return render_template(
        "training_select.html",
        entries=vocabulary_service.list_entries(),
    )


@training_bp.route("/training", methods=["POST"])
@login_required
def create_training():
    if request.is_json:
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify({"error": "Invalid request"}), 400
        vocabulary_ids = data.get("vocabulary_ids")
    else:
        vocabulary_ids = request.form.getlist("vocabulary_ids")

    training_session, error = training_service.create_training_session(
        session["user_id"],
        vocabulary_ids,
    )
    if error:
        if request.is_json:
            return jsonify({"error": error}), 400
        return render_template(
            "training_select.html",
            entries=vocabulary_service.list_entries(),
            error=error,
        ), 400

    if request.is_json:
        return jsonify(training_service.get_training_quiz(training_session["id"], session["user_id"])), 201
    return redirect(f"/training/{training_session['id']}")


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
