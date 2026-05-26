import click
from flask import current_app
from flask.cli import with_appcontext

from Services.user_service import user_service
from db import init_db


def register_cli_commands(app):
    app.cli.add_command(create_admin)
    app.cli.add_command(init_database)


@click.command("create-admin")
@click.option("--username", prompt="User id")
@click.password_option("--password", confirmation_prompt=True)
@with_appcontext
def create_admin(username, password):
    user, error = user_service.create_admin(username, password)
    if error:
        raise click.ClickException(error)

    click.echo(
        f"Created admin user '{user['username']}'. "
        "Existing admins were moved to trusted."
    )


@click.command("init-db")
@with_appcontext
def init_database():
    init_db(current_app)
    click.echo("Initialized the database.")
