from functools import wraps

import re
from xml.sax.saxutils import escape

from flask import Blueprint, Response, current_app, flash, jsonify, redirect, render_template, request, session, url_for

from csrf import csrf_required
from Services.ai_quota_service import ai_quota_service
from Services.user_service import ACCOUNT_CATEGORY_ADMIN, ACCOUNT_CATEGORY_TRUSTED, user_service
from Services.vocabulary_ai_service import vocabulary_ai_service
from Services.vocabulary_domains import MAX_VOCABULARY_DOMAINS, active_vocabulary_domains
from Services.vocabulary_service import vocabulary_service
from Services.vocabulary_gre import GRE_RATING_FILTERS


vocabulary_bp = Blueprint("vocabulary", __name__)
PART_OF_SPEECH_FILTERS = [
    ("noun", "Noun"),
    ("verb", "Verb"),
    ("adjective", "Adjective"),
    ("adverb", "Adverb"),
    ("phrase", "Phrase"),
    ("other", "Other"),
]
FREQUENCY_BAND_FILTERS = [
    ("common", "Common"),
    ("uncommon", "Uncommon"),
    ("rare", "Rare"),
    ("very_rare", "Very rare"),
    ("archaic_or_obsolete", "Archaic or obsolete"),
    ("specialized", "Specialized"),
]
WORD_SLUG_PATTERN = re.compile(r"[^a-z0-9]+")


def vocabulary_word_slug(word):
    return WORD_SLUG_PATTERN.sub("-", (word or "").lower()).strip("-")


def public_entry(entry):
    visible_entry = dict(entry)
    visible_entry["slug"] = vocabulary_word_slug(visible_entry["word"])
    visible_entry["linked_synonyms"] = [
        {
            **synonym,
            "linked_slug": vocabulary_word_slug(synonym["linked_word"])
            if synonym.get("linked_word")
            else None,
        }
        for synonym in visible_entry.get("linked_synonyms", [])
    ]
    return visible_entry


def public_entries(entries):
    return [public_entry(entry) for entry in entries]


def find_public_entries_by_slug(slug):
    slug = (slug or "").strip().lower()
    if not slug:
        return []
    return [
        public_entry(entry)
        for entry in vocabulary_service.list_entries()
        if vocabulary_word_slug(entry["word"]) == slug
    ]


def public_word_page_metadata(entries):
    word = entries[0]["word"]
    word_title = word[:1].upper() + word[1:]
    first_definition = entries[0]["definition"]
    return {
        "title": f"{word_title} Meaning, Definition, Synonyms, and Examples | eruditeEdge",
        "description": (
            f"Learn the meaning of {word} with a clear definition, examples, "
            "synonyms, and usage notes."
        ),
        "heading": f"{word_title} Meaning",
        "structured_data": {
            "@context": "https://schema.org",
            "@type": "DefinedTerm",
            "name": word,
            "description": first_definition,
        },
    }


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


def vocabulary_read_entry(entry):
    readable_entry = dict(entry)
    readable_entry.pop("created_by", None)
    return readable_entry


def vocabulary_read_entries(entries):
    return [vocabulary_read_entry(entry) for entry in entries]


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
    sources = form.get("sources", "").splitlines()
    selected_domains = form.getlist("domains")
    ordered_domain_candidates = [
        item.strip()
        for item in form.get("domains_order", "").split(",")
        if item.strip()
    ]
    if not selected_domains:
        selected_domains = ordered_domain_candidates
    domains = [
        domain
        for domain in ordered_domain_candidates
        if domain in selected_domains
    ]
    domains.extend(
        domain
        for domain in selected_domains
        if domain not in domains
    )
    return {
        "word": form.get("word"),
        "definition": form.get("definition"),
        "context": form.get("context"),
        "part_of_speech": form.get("part_of_speech"),
        "frequency_band": form.get("frequency_band"),
        "frequency_note": form.get("frequency_note"),
        "gre_rating": form.get("gre_rating"),
        "domains": domains,
        "synonyms": synonyms,
        "examples": examples,
        "cloze_sentences": cloze_sentences,
        "sources": sources,
        "needs_attention": form.get("needs_attention"),
        "confidence_score": form.get("confidence_score"),
    }


def sources_to_text(sources):
    lines = []
    for source in sources or []:
        parts = [source.get("name", "")]
        if source.get("author") or source.get("note"):
            parts.append(source.get("author") or "")
        if source.get("note"):
            parts.append(source.get("note"))
        lines.append("; ".join(parts))
    return "\n".join(lines)


def vocabulary_filter_choices():
    return {
        "domains": active_vocabulary_domains(),
        "parts_of_speech": PART_OF_SPEECH_FILTERS,
        "frequency_bands": FREQUENCY_BAND_FILTERS,
        "gre_ratings": GRE_RATING_FILTERS,
        "gre_lists": vocabulary_service.list_gre_word_lists(),
    }


def vocabulary_filters_from_request(args):
    return {
        "word": args.get("word", "").strip(),
        "source_name": args.get("source_name", "").strip(),
        "source_author": args.get("source_author", "").strip(),
        "context": args.get("context", "").strip(),
        "domain": args.get("domain", "").strip(),
        "part_of_speech": args.get("part_of_speech", "").strip(),
        "frequency_band": args.get("frequency_band", "").strip(),
        "gre_rating": args.get("gre_rating", "").strip(),
        "gre_lists": args.getlist("gre_list"),
    }


def active_vocabulary_filters(filters, filter_choices=None):
    active_filters = {
        key: value
        for key, value in filters.items()
        if value and key != "gre_lists"
    }
    gre_lists = filters.get("gre_lists", [])
    if gre_lists:
        names_by_key = {
            word_list["list_key"]: word_list["name"]
            for word_list in (filter_choices or {}).get("gre_lists", [])
        }
        active_filters["GRE lists"] = ", ".join(
            names_by_key.get(list_key, list_key)
            for list_key in gre_lists
        )
    return active_filters


@vocabulary_bp.route("/words", methods=["GET"])
def public_words():
    entries = public_entries(vocabulary_service.list_entries())
    return render_template(
        "public_words.html",
        entries=entries,
    )


@vocabulary_bp.route("/words/<word_slug>", methods=["GET"])
def public_word(word_slug):
    if word_slug.endswith("-meaning"):
        meaning_base_slug = word_slug[: -len("-meaning")]
        entries = find_public_entries_by_slug(meaning_base_slug)
        if entries:
            return redirect(
                url_for("vocabulary.public_word", word_slug=entries[0]["slug"]),
                code=301,
            )

    entries = find_public_entries_by_slug(word_slug)
    if not entries:
        return render_template("public_word_not_found.html", word_slug=word_slug), 404

    canonical_slug = entries[0]["slug"]
    if word_slug != canonical_slug:
        return redirect(url_for("vocabulary.public_word", word_slug=canonical_slug), code=301)

    return render_template(
        "public_word.html",
        entries=entries,
        metadata=public_word_page_metadata(entries),
        canonical_url=url_for(
            "vocabulary.public_word",
            word_slug=canonical_slug,
            _external=True,
        ),
    )


@vocabulary_bp.route("/sitemap.xml", methods=["GET"])
def sitemap():
    word_urls = []
    seen_slugs = set()
    for entry in vocabulary_service.list_entries():
        slug = vocabulary_word_slug(entry["word"])
        if slug in seen_slugs:
            continue
        seen_slugs.add(slug)
        word_urls.append(
            url_for("vocabulary.public_word", word_slug=slug, _external=True)
        )
    urls = [
        url_for("index", _external=True),
        url_for("vocabulary.public_words", _external=True),
        *word_urls,
    ]
    body = "\n".join(
        [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
            *[f"  <url><loc>{escape(url)}</loc></url>" for url in urls],
            "</urlset>",
        ]
    )
    return Response(body, mimetype="application/xml")


@vocabulary_bp.route("/robots.txt", methods=["GET"])
def robots_txt():
    body = "\n".join(
        [
            "User-agent: *",
            "Allow: /",
            f"Sitemap: {url_for('vocabulary.sitemap', _external=True)}",
            "",
        ]
    )
    return Response(body, mimetype="text/plain")


@vocabulary_bp.route("/vocabulary", methods=["GET"])
def vocabulary_list():
    filters = vocabulary_filters_from_request(request.args)
    if not is_admin():
        filters["domain"] = ""
    filter_choices = vocabulary_filter_choices()
    entries, error = vocabulary_service.search_entries(filters)
    if error:
        flash(error)
        entries = []
    user_id = session.get("user_id")
    return render_template(
        "vocabulary_list.html",
        entries=entries_with_ownership(entries, user_id),
        filters=filters,
        active_filters=active_vocabulary_filters(filters, filter_choices),
        filter_choices=filter_choices,
        search_word=filters["word"],
    )


@vocabulary_bp.route("/vocabulary/new", methods=["GET"])
@page_vocabulary_manager_required
def new_vocabulary():
    return render_template(
        "vocabulary_form.html",
        entry=None,
        prefill_word=request.args.get("word", "").strip(),
        available_domains=active_vocabulary_domains(),
        max_domains=MAX_VOCABULARY_DOMAINS,
    )


@vocabulary_bp.route("/vocabulary/new", methods=["POST"])
@page_vocabulary_manager_required
@csrf_required
def create_new_vocabulary_page():
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
            cloze_sentences_text=request.form.get("cloze_sentences", ""),
            sources_text=request.form.get("sources", ""),
            available_domains=active_vocabulary_domains(),
            max_domains=MAX_VOCABULARY_DOMAINS,
        ), 400
    return redirect(f"/vocabulary/{entry['id']}/page")


@vocabulary_bp.route("/vocabulary", methods=["POST"])
@vocabulary_manager_required
@csrf_required
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
        data.get("usage_clue"),
    )
    if error:
        ai_quota_service.refund_generation(user)
        return jsonify({"error": error}), 400

    values, error = vocabulary_service.validate_entry_data(entry)
    if error:
        ai_quota_service.refund_generation(user)
        return jsonify({"error": error}), 400
    values.pop("definition_key", None)
    values.pop("sources", None)
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
def search_vocabulary():
    entries, error = vocabulary_service.search_by_word(request.args.get("word"))
    if error:
        return jsonify({"error": error}), 400
    return jsonify(vocabulary_read_entries(entries))


@vocabulary_bp.route("/vocabulary/<int:vocabulary_id>", methods=["GET"])
def view_vocabulary(vocabulary_id):
    entry = vocabulary_service.get_entry(vocabulary_id)
    if not entry:
        return jsonify({"error": "Vocabulary entry was not found"}), 404
    return jsonify(vocabulary_read_entry(entry))


@vocabulary_bp.route("/vocabulary/<int:vocabulary_id>/page", methods=["GET"])
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


@vocabulary_bp.route("/vocabulary/<int:vocabulary_id>/edit", methods=["GET"])
@page_vocabulary_manager_required
def edit_vocabulary(vocabulary_id):
    entry = vocabulary_service.get_entry(vocabulary_id)
    if not entry:
        flash("Vocabulary entry was not found")
        return redirect("/vocabulary")

    return render_template(
        "vocabulary_form.html",
        entry=entry,
        examples_text="\n".join(entry["examples"]),
        cloze_sentences_text="\n".join(entry["cloze_sentences"]),
        sources_text=sources_to_text(entry.get("sources", [])),
        available_domains=active_vocabulary_domains(),
        max_domains=MAX_VOCABULARY_DOMAINS,
    )


@vocabulary_bp.route("/vocabulary/<int:vocabulary_id>/edit", methods=["POST"])
@page_vocabulary_manager_required
@csrf_required
def update_vocabulary_page(vocabulary_id):
    entry = vocabulary_service.get_entry(vocabulary_id)
    if not entry:
        flash("Vocabulary entry was not found")
        return redirect("/vocabulary")

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
            sources_text=request.form.get("sources", ""),
            available_domains=active_vocabulary_domains(),
            max_domains=MAX_VOCABULARY_DOMAINS,
        ), 400
    return redirect(f"/vocabulary/{updated_entry['id']}/page")


@vocabulary_bp.route("/vocabulary/<int:vocabulary_id>", methods=["PUT"])
@vocabulary_manager_required
@csrf_required
def update_vocabulary(vocabulary_id):
    data = request.get_json(silent=True) or request.form
    entry, error = vocabulary_service.update_entry(vocabulary_id, data)
    if error:
        return jsonify({"error": error}), 400
    return jsonify(entry)
