import unittest
from unittest.mock import patch

import storage.db as db


class ResolveDbPathTests(unittest.TestCase):
    def test_sqlite_relative_path(self) -> None:
        with patch.object(db, "DATABASE_URL", "sqlite:///newshive.db"), patch.object(db, "SQLITE_PATH", "fallback.db"):
            self.assertEqual(db._resolve_db_path(), "newshive.db")

    def test_sqlite_absolute_path(self) -> None:
        with patch.object(db, "DATABASE_URL", "sqlite:////tmp/newshive.db"), patch.object(db, "SQLITE_PATH", "fallback.db"):
            self.assertEqual(db._resolve_db_path(), "/tmp/newshive.db")

    def test_empty_database_url_uses_sqlite_path_fallback(self) -> None:
        with patch.object(db, "DATABASE_URL", ""), patch.object(db, "SQLITE_PATH", "sqlite-fallback.db"):
            self.assertEqual(db._resolve_db_path(), "sqlite-fallback.db")


if __name__ == "__main__":
    unittest.main()
