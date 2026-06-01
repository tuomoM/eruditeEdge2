import os
import unittest
from unittest.mock import patch

import config


class ConfigTestCase(unittest.TestCase):
    def test_database_uses_explicit_database_env(self):
        with patch.dict(
            os.environ,
            {
                "DATABASE": "/tmp/custom-erudite-edge.db",
                "RAILWAY_VOLUME_MOUNT_PATH": "/app/data",
            },
            clear=True,
        ):
            self.assertEqual(
                config._default_database_path(),
                "/tmp/custom-erudite-edge.db",
            )

    def test_database_defaults_to_railway_volume_when_present(self):
        with patch.dict(
            os.environ,
            {"RAILWAY_VOLUME_MOUNT_PATH": "/app/data"},
            clear=True,
        ):
            self.assertEqual(
                config._default_database_path(),
                "/app/data/database.db",
            )

    def test_database_defaults_to_local_database_without_volume(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(
                config._default_database_path(),
                os.path.join(config.BASE_DIR, "database.db"),
            )


if __name__ == "__main__":
    unittest.main()
