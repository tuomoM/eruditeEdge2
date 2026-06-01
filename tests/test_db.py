import os
import tempfile
import unittest

import db
from app import create_app


class DatabaseConnectionTestCase(unittest.TestCase):
    def test_get_connection_creates_database_parent_directory(self):
        with tempfile.TemporaryDirectory() as temp_directory:
            database_path = os.path.join(
                temp_directory,
                "railway-volume",
                "database.db",
            )
            app = create_app(
                {
                    "TESTING": True,
                    "DATABASE": database_path,
                    "SECRET_KEY": "test-secret-key",
                }
            )

            with app.app_context():
                connection = db.get_connection()
                connection.execute("SELECT 1")

            self.assertTrue(os.path.isdir(os.path.dirname(database_path)))
            self.assertTrue(os.path.exists(database_path))

    def test_get_connection_allows_in_memory_database(self):
        app = create_app(
            {
                "TESTING": True,
                "DATABASE": ":memory:",
                "SECRET_KEY": "test-secret-key",
            }
        )

        with app.app_context():
            connection = db.get_connection()
            result = connection.execute("SELECT 1 AS value").fetchone()

        self.assertEqual(result["value"], 1)


if __name__ == "__main__":
    unittest.main()
