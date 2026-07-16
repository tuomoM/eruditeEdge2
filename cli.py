import os
import sqlite3

import click
from flask import current_app
from flask.cli import with_appcontext

from Services.user_service import user_service
from Services.background_job_service import (
    GENERATE_SYNONYM_NET_CLOZE_JOB,
    LINK_VOCABULARY_SYNONYMS_JOB,
    background_job_service,
)
from Services.synonym_net_cloze_service import synonym_net_cloze_service
from Services.vocabulary_synonym_link_service import vocabulary_synonym_link_service
from Services.vocabulary_service import vocabulary_service
from Services.vocabulary_maintenance_service import vocabulary_maintenance_service
from db import get_connection, init_db


MIGRATION_MARKERS = {
    "001_training_quiz.sql": {
        "columns": {
            "training_sessions": ["submitted_at", "score", "total"],
            "training_items": ["question_token", "word", "context", "definition"],
        },
        "tables": ["training_answer_options", "training_incorrect_answers"],
    },
    "002_user_account_categories.sql": {
        "columns": {"users": ["account_category"]},
    },
    "003_ai_generation_usage.sql": {
        "tables": ["ai_generation_usage"],
    },
    "004_invite_codes.sql": {
        "tables": ["invite_codes"],
    },
    "005_invite_code_usage.sql": {
        "columns": {"invite_codes": ["used_by", "used_at"]},
    },
    "006_google_registration.sql": {
        "columns": {"users": ["google_sub", "google_email"]},
    },
    "007_access_requests.sql": {
        "tables": ["access_requests"],
    },
    "008_access_request_guardrails.sql": {
        "columns": {"access_requests": ["ip_address"]},
    },
    "009_access_request_unique_email.sql": {
        "indexes": ["access_requests_email_unique"],
    },
    "010_cloze_training.sql": {
        "columns": {
            "vocabulary_entries": ["part_of_speech"],
            "training_sessions": ["training_type"],
            "training_items": ["question_type", "prompt_text"],
            "training_answer_options": ["option_text"],
            "training_incorrect_answers": [
                "question_type",
                "prompt_text",
                "correct_answer",
                "selected_answer",
            ],
        },
        "tables": ["vocabulary_cloze_sentences"],
    },
    "011_vocabulary_domains.sql": {
        "tables": ["vocabulary_domains"],
    },
    "013_vocabulary_ai_assessment.sql": {
        "columns": {
            "vocabulary_entries": [
                "needs_attention",
                "confidence_score",
                "confidence_obsolete",
            ],
        },
    },
    "014_vocabulary_synonym_links_and_jobs.sql": {
        "columns": {
            "vocabulary_synonyms": ["linked_vocabulary_id"],
        },
        "tables": ["background_jobs"],
        "indexes": [
            "vocabulary_synonyms_linked_vocabulary_id_idx",
            "vocabulary_synonyms_synonym_nocase_idx",
            "background_jobs_status_type_idx",
        ],
    },
    "015_vocabulary_sources.sql": {
        "tables": ["vocabulary_sources", "vocabulary_entry_sources"],
        "indexes": [
            "vocabulary_sources_name_author_idx",
            "vocabulary_entry_sources_vocabulary_id_idx",
            "vocabulary_entry_sources_source_id_idx",
        ],
    },
    "016_vocabulary_senses_and_frequency.sql": {
        "columns": {
            "vocabulary_entries": [
                "definition_key",
                "frequency_band",
                "frequency_note",
            ],
        },
        "indexes": ["vocabulary_entries_sense_unique_idx"],
    },
    "017_vocabulary_maintenance_runs.sql": {
        "tables": [
            "vocabulary_maintenance_runs",
            "vocabulary_maintenance_items",
            "vocabulary_maintenance_promotions",
        ],
        "indexes": [
            "vocabulary_maintenance_runs_status_idx",
            "vocabulary_maintenance_items_run_status_idx",
            "vocabulary_maintenance_items_vocabulary_idx",
            "vocabulary_maintenance_promotions_run_idx",
        ],
    },
    "018_vocabulary_domain_model_proposals.sql": {
        "tables": ["vocabulary_domain_model_proposals"],
        "indexes": ["vocabulary_domain_model_proposals_status_idx"],
    },
}


def register_cli_commands(app):
    app.cli.add_command(create_admin)
    app.cli.add_command(rotate_admin)
    app.cli.add_command(init_database)
    app.cli.add_command(migrate_database)
    app.cli.add_command(check_database)
    app.cli.add_command(run_background_jobs)
    app.cli.add_command(generate_synonym_cloze)
    app.cli.add_command(create_vocabulary_maintenance_run)
    app.cli.add_command(generate_vocabulary_domain_model)


@click.command("create-admin")
@click.option("--username", prompt="User id")
@click.password_option("--password", confirmation_prompt=True)
@with_appcontext
def create_admin(username, password):
    user, error = user_service.create_admin(username, password)
    if error:
        raise click.ClickException(error)

    click.echo(f"Created admin user '{user['username']}'.")


@click.command("rotate-admin")
@with_appcontext
def rotate_admin():
    if current_app.config["ROTATE_ADMIN_ALLOWED"] != "YES":
        raise click.ClickException("Admin rotation is not allowed")

    admin_username = click.prompt("Admin user id")
    admin_password = click.prompt("Admin password", hide_input=True)
    trusted_username = click.prompt("Trusted user id")
    confirmation = click.prompt(
        f"Are you sure you want to rotate admin role to user: {trusted_username}",
        default="n",
        show_default=False,
    )
    if confirmation.lower() not in {"y", "yes"}:
        click.echo("Admin rotation aborted.")
        return

    user, error = user_service.rotate_admin(
        admin_username,
        admin_password,
        trusted_username,
    )
    if error:
        raise click.ClickException(error)

    click.echo(f"Rotated admin role to '{user['username']}'.")


@click.command("init-db")
@with_appcontext
def init_database():
    init_db(current_app)
    click.echo("Initialized the database.")


@click.command("migrate")
@with_appcontext
def migrate_database():
    connection = get_connection()
    _ensure_schema_migrations_table(connection)
    applied_migrations = _applied_migrations(connection)
    migration_files = _migration_files()
    applied_count = 0
    stamped_count = 0

    for migration_file in migration_files:
        if migration_file in applied_migrations:
            continue

        if _migration_schema_is_present(connection, migration_file):
            _record_migration(connection, migration_file)
            stamped_count += 1
            click.echo(f"Stamped {migration_file}.")
            continue

        migration_path = os.path.join(current_app.root_path, "migrations", migration_file)
        try:
            with open(migration_path, encoding="utf-8") as migration:
                connection.executescript(migration.read())
            _record_migration(connection, migration_file)
            connection.commit()
        except sqlite3.Error as error:
            connection.rollback()
            raise click.ClickException(
                f"Migration {migration_file} failed: {error}"
            ) from error
        applied_count += 1
        click.echo(f"Applied {migration_file}.")

    if applied_count == 0 and stamped_count == 0:
        click.echo("No pending migrations.")
    else:
        click.echo(
            f"Migration complete. Applied {applied_count}, stamped {stamped_count}."
        )


@click.command("check-database")
@with_appcontext
def check_database():
    click.echo(f"Database: {current_app.config['DATABASE']}")

    if os.environ.get("RAILWAY_VOLUME_MOUNT_PATH"):
        click.echo(f"Railway volume: {os.environ['RAILWAY_VOLUME_MOUNT_PATH']}")
        return

    if os.environ.get("DATABASE"):
        click.echo("Database path is set explicitly.")
        return

    if _is_railway_environment():
        raise click.ClickException(
            "Railway deployment has no persistent database path. "
            "Attach a Railway volume or set DATABASE to a persistent path."
        )

    click.echo("No Railway volume detected; using the local database path.")


@click.command("run-background-jobs")
@click.option("--limit", default=10, show_default=True, type=click.IntRange(1, 100))
@with_appcontext
def run_background_jobs(limit):
    background_job_service.register_handler(
        LINK_VOCABULARY_SYNONYMS_JOB,
        lambda payload: vocabulary_synonym_link_service.link_vocabulary_synonyms(
            payload["vocabulary_id"],
        ),
    )
    background_job_service.register_handler(
        GENERATE_SYNONYM_NET_CLOZE_JOB,
        _run_synonym_net_cloze_job,
    )
    summary = background_job_service.run_pending(limit)
    click.echo(
        "Processed {processed}, completed {completed}, failed {failed}.".format(
            **summary,
        )
    )
    repair_summary = vocabulary_synonym_link_service.repair_all_vocabulary_synonyms()
    click.echo(
        "Synonym repair checked {entries} entries, linked {linked}, ambiguous {ambiguous}.".format(
            **repair_summary,
        )
    )


def _run_synonym_net_cloze_job(payload):
    _, error = synonym_net_cloze_service.generate_for_vocabulary(
        payload["vocabulary_id"],
        current_app.config["OPENAI_API_KEY"],
        current_app.config["OPENAI_MODEL"],
    )
    if error:
        raise click.ClickException(error)


@click.command("generate-synonym-cloze")
@click.argument("entry")
@with_appcontext
def generate_synonym_cloze(entry):
    vocabulary_id = _resolve_vocabulary_id(entry)

    result, error = synonym_net_cloze_service.generate_for_vocabulary(
        vocabulary_id,
        current_app.config["OPENAI_API_KEY"],
        current_app.config["OPENAI_MODEL"],
    )
    if error:
        raise click.ClickException(error)

    if result["updated"]:
        click.echo(f"Generated synonym-specific cloze data for {result['updated']} entries.")
    else:
        click.echo(result["skipped"])


@click.command("create-vocabulary-maintenance-run")
@click.option("--name", required=True, help="Run name, such as domain-frequency-v2.")
@click.option(
    "--scope",
    required=True,
    type=click.Choice(
        [
            "all",
            "missing-domains",
            "domain",
            "context",
            "frequency-band",
            "created-after",
            "ids",
            "source",
        ]
    ),
)
@click.option("--domain", help="Domain filter for --scope domain.")
@click.option("--context", help="Context filter for --scope context.")
@click.option("--frequency-band", help="Frequency filter for --scope frequency-band.")
@click.option("--created-after", help="Created-at lower bound for --scope created-after.")
@click.option("--ids", help="Comma-separated vocabulary ids for --scope ids.")
@click.option("--source-name", help="Source title filter for --scope source.")
@click.option("--source-author", help="Source author filter for --scope source.")
@click.option("--max-items", type=click.IntRange(1), help="Maximum selected entries.")
@click.option(
    "--max-estimated-cost",
    type=click.FloatRange(0),
    help="Maximum accepted estimated processing cost.",
)
@click.option("--dry-run", is_flag=True, help="Preview without creating a run.")
@click.option(
    "--confirm-production",
    is_flag=True,
    help="Required for non-dry-run creation outside local/test environments.",
)
@with_appcontext
def create_vocabulary_maintenance_run(
    name,
    scope,
    domain,
    context,
    frequency_band,
    created_after,
    ids,
    source_name,
    source_author,
    max_items,
    max_estimated_cost,
    dry_run,
    confirm_production,
):
    app_env = current_app.config["APP_ENV"]
    if (
        not dry_run
        and app_env not in {"development", "dev", "local", "testing", "test"}
        and not confirm_production
    ):
        raise click.ClickException(
            "Use --confirm-production to create a maintenance run in this environment"
        )

    maintenance_model = current_app.config.get("OPENAI_MAINTENANCE_MODEL")
    model = maintenance_model or current_app.config["OPENAI_MODEL"]
    prepared_run, error = vocabulary_maintenance_service.prepare_run(
        name=name,
        scope=scope,
        ai_model=model,
        max_items=max_items,
        max_estimated_cost=max_estimated_cost,
        domain=domain,
        context=context,
        frequency_band=frequency_band,
        created_after=created_after,
        ids=ids,
        source_name=source_name,
        source_author=source_author,
    )
    if error:
        raise click.ClickException(error)

    click.echo(f"Environment: {app_env}")
    click.echo(f"Database: {current_app.config['DATABASE']}")
    click.echo(f"Selected entries: {prepared_run['selected_count']}")
    click.echo(f"AI model: {model}")
    if not maintenance_model:
        click.echo("AI model source: OPENAI_MODEL fallback")
    else:
        click.echo("AI model source: OPENAI_MAINTENANCE_MODEL")
    click.echo(
        "Estimated tokens: {input_tokens} input, {output_tokens} output".format(
            input_tokens=prepared_run["estimated_input_tokens"],
            output_tokens=prepared_run["estimated_output_tokens"],
        )
    )
    click.echo(f"Estimated cost: {prepared_run['estimated_cost']:.2f}")
    click.echo(f"Mode: {'dry-run' if dry_run else 'create'}")

    if dry_run:
        click.echo("No maintenance run created.")
        return

    run_id = vocabulary_maintenance_service.create_run(prepared_run)
    click.echo(f"Created vocabulary maintenance run #{run_id}.")


@click.command("generate-vocabulary-domain-model")
@click.option("--name", required=True, help="Proposal name, such as domain-model-v2.")
@click.option(
    "--scope",
    default="all",
    show_default=True,
    type=click.Choice(
        [
            "all",
            "missing-domains",
            "domain",
            "context",
            "frequency-band",
            "created-after",
            "ids",
            "source",
        ]
    ),
)
@click.option("--domain", help="Domain filter for --scope domain.")
@click.option("--context", help="Context filter for --scope context.")
@click.option("--frequency-band", help="Frequency filter for --scope frequency-band.")
@click.option("--created-after", help="Created-at lower bound for --scope created-after.")
@click.option("--ids", help="Comma-separated vocabulary ids for --scope ids.")
@click.option("--source-name", help="Source title filter for --scope source.")
@click.option("--source-author", help="Source author filter for --scope source.")
@click.option("--max-items", type=click.IntRange(1), help="Maximum selected entries.")
@click.option(
    "--max-estimated-cost",
    type=click.FloatRange(0),
    help="Maximum accepted estimated processing cost.",
)
@click.option("--dry-run", is_flag=True, help="Preview without calling AI.")
@click.option(
    "--confirm-production",
    is_flag=True,
    help="Required for non-dry-run generation outside local/test environments.",
)
@with_appcontext
def generate_vocabulary_domain_model(
    name,
    scope,
    domain,
    context,
    frequency_band,
    created_after,
    ids,
    source_name,
    source_author,
    max_items,
    max_estimated_cost,
    dry_run,
    confirm_production,
):
    app_env = current_app.config["APP_ENV"]
    if (
        not dry_run
        and app_env not in {"development", "dev", "local", "testing", "test"}
        and not confirm_production
    ):
        raise click.ClickException(
            "Use --confirm-production to generate a domain model in this environment"
        )

    maintenance_model = current_app.config.get("OPENAI_MAINTENANCE_MODEL")
    model = maintenance_model or current_app.config["OPENAI_MODEL"]
    prepared_proposal, error = vocabulary_maintenance_service.prepare_domain_model_proposal(
        name=name,
        scope=scope,
        ai_model=model,
        max_items=max_items,
        max_estimated_cost=max_estimated_cost,
        domain=domain,
        context=context,
        frequency_band=frequency_band,
        created_after=created_after,
        ids=ids,
        source_name=source_name,
        source_author=source_author,
    )
    if error:
        raise click.ClickException(error)

    click.echo(f"Environment: {app_env}")
    click.echo(f"Database: {current_app.config['DATABASE']}")
    click.echo(f"Selected entries: {prepared_proposal['selected_count']}")
    click.echo(f"AI model: {model}")
    if not maintenance_model:
        click.echo("AI model source: OPENAI_MODEL fallback")
    else:
        click.echo("AI model source: OPENAI_MAINTENANCE_MODEL")
    click.echo(
        f"OpenAI timeout: {current_app.config['OPENAI_MAINTENANCE_TIMEOUT_SECONDS']}s"
    )
    click.echo(
        "Estimated tokens: {input_tokens} input, {output_tokens} output".format(
            input_tokens=prepared_proposal["estimated_input_tokens"],
            output_tokens=prepared_proposal["estimated_output_tokens"],
        )
    )
    click.echo(f"Estimated cost: {prepared_proposal['estimated_cost']:.2f}")
    click.echo(f"Mode: {'dry-run' if dry_run else 'generate'}")

    if dry_run:
        click.echo("No AI request made and no domain model proposal created.")
        return

    result, error = vocabulary_maintenance_service.generate_domain_model_proposal(
        prepared_proposal,
        current_app.config["OPENAI_API_KEY"],
        timeout_seconds=current_app.config["OPENAI_MAINTENANCE_TIMEOUT_SECONDS"],
    )
    if error:
        raise click.ClickException(error)

    click.echo(f"Created vocabulary domain model proposal #{result['id']}.")
    click.echo(f"Proposed domains: {len(result['proposal']['domains'])}")
    click.echo(f"Proposed graph edges: {len(result['proposal']['domain_edges'])}")


def _resolve_vocabulary_id(entry):
    target = entry.strip()
    if target.isdigit():
        vocabulary_id = int(target)
        if vocabulary_service.get_entry(vocabulary_id):
            return vocabulary_id
        raise click.ClickException("Vocabulary entry was not found")

    matches = vocabulary_service.find_entries_by_exact_word(target)
    if not matches:
        raise click.ClickException("Vocabulary entry was not found")
    if len(matches) == 1:
        return matches[0]["id"]

    lines = [f"Multiple vocabulary entries match '{target}'. Use one of these ids:"]
    for match in matches:
        lines.append(
            "#{id}: {word} ({part_of_speech}, {context}) - {definition}".format(
                id=match["id"],
                word=match["word"],
                part_of_speech=match["part_of_speech"],
                context=match["context"] or "unspecified",
                definition=match["definition"],
            )
        )
    raise click.ClickException("\n".join(lines))


def _is_railway_environment():
    return any(
        os.environ.get(key)
        for key in (
            "RAILWAY_ENVIRONMENT",
            "RAILWAY_PROJECT_ID",
            "RAILWAY_SERVICE_ID",
        )
    )


def _ensure_schema_migrations_table(connection):
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            filename TEXT PRIMARY KEY,
            applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    connection.commit()


def _applied_migrations(connection):
    return {
        row["filename"]
        for row in connection.execute(
            "SELECT filename FROM schema_migrations"
        ).fetchall()
    }


def _migration_files():
    migrations_path = os.path.join(current_app.root_path, "migrations")
    return sorted(
        filename
        for filename in os.listdir(migrations_path)
        if filename.endswith(".sql")
    )


def _record_migration(connection, filename):
    connection.execute(
        "INSERT OR IGNORE INTO schema_migrations (filename) VALUES (?)",
        [filename],
    )
    connection.commit()


def _migration_schema_is_present(connection, filename):
    marker = MIGRATION_MARKERS.get(filename)
    if not marker:
        return False

    for table in marker.get("tables", []):
        if not _table_exists(connection, table):
            return False

    for table, columns in marker.get("columns", {}).items():
        existing_columns = _table_columns(connection, table)
        if not existing_columns:
            return False
        if not set(columns).issubset(existing_columns):
            return False

    for index in marker.get("indexes", []):
        if not _index_exists(connection, index):
            return False

    return True


def _table_exists(connection, table):
    row = connection.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type = 'table' AND name = ?
        """,
        [table],
    ).fetchone()
    return row is not None


def _table_columns(connection, table):
    return {
        row["name"]
        for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
    }


def _index_exists(connection, index):
    row = connection.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type = 'index' AND name = ?
        """,
        [index],
    ).fetchone()
    return row is not None
