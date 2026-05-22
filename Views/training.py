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
    data = request.get_json(silent=True)
    if data is not None:
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
        return jsonify(training_session), 201
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
    return render_template("training_detail.html", training=training_session)
