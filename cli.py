import os
import sqlite3

import click
from flask import current_app
from flask.cli import with_appcontext

from Services.user_service import user_service
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
}


def register_cli_commands(app):
    app.cli.add_command(create_admin)
    app.cli.add_command(rotate_admin)
    app.cli.add_command(init_database)
    app.cli.add_command(migrate_database)
    app.cli.add_command(check_database)


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
