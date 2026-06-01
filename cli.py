import os

import click
from flask import current_app
from flask.cli import with_appcontext

from Services.user_service import user_service
from db import init_db


def register_cli_commands(app):
    app.cli.add_command(create_admin)
    app.cli.add_command(rotate_admin)
    app.cli.add_command(init_database)
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
