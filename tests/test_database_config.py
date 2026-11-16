import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.config import Settings
from app.database import normalize_database_url


class DatabaseConfigTests(unittest.TestCase):
    def test_local_env_file_overrides_base_env_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base_env = Path(directory) / ".env"
            local_env = Path(directory) / ".env.local"
            base_env.write_text("DATABASE_URL=postgresql://base.example/db\n", encoding="utf-8")
            local_env.write_text(
                "DATABASE_URL=postgresql://local.example/db\n",
                encoding="utf-8",
            )

            with patch.dict(os.environ, {}, clear=True):
                settings = Settings(_env_file=(base_env, local_env))

        self.assertEqual(settings.database_url, "postgresql://local.example/db")

    def test_normalizes_neon_postgres_url_for_asyncpg(self) -> None:
        url = normalize_database_url(
            "postgresql://user:password@ep-example-pooler.neon.tech/app"
            "?sslmode=require&channel_binding=require"
        )

        self.assertEqual(url.drivername, "postgresql+asyncpg")
        self.assertEqual(url.host, "ep-example-pooler.neon.tech")
        self.assertEqual(url.query["ssl"], "require")
        self.assertNotIn("sslmode", url.query)
        self.assertNotIn("channel_binding", url.query)

    def test_preserves_existing_asyncpg_url(self) -> None:
        url = normalize_database_url(
            "postgresql+asyncpg://user:password@localhost/app"
        )

        self.assertEqual(url.drivername, "postgresql+asyncpg")
