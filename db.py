import os
import sqlite3
from flask import current_app, g


def _ensure_database_directory(database_path):
    if database_path == ":memory:":
        return

    parent_directory = os.path.dirname(database_path)
    if parent_directory:
        os.makedirs(parent_directory, exist_ok=True)


def get_connection():
    if "db" not in g:
        database_path = current_app.config["DATABASE"]
        _ensure_database_directory(database_path)
        g.db = sqlite3.connect(database_path)
        g.db.execute("PRAGMA foreign_keys = ON")
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
