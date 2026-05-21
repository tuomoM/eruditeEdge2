import sqlite3
from flask import current_app, g


def get_connection():
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
    return g.db


def close_connection(error=None):
    connection = g.pop("db", None)
    if connection is not None:
        connection.close()


def execute(sql, params=None):
    connection = get_connection()
    cursor = connection.execute(sql, params or [])
    connection.commit()
    return cursor


def query(sql, params=None):
    cursor = get_connection().execute(sql, params or [])
    return cursor.fetchall()


def init_db(app):
    with app.app_context():
        connection = get_connection()
        with app.open_resource("schema.sql") as schema_file:
            connection.executescript(schema_file.read().decode("utf-8"))
        connection.commit()
