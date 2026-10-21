"""CLI integration checks against local PostgreSQL and real age/pg tools.

Run with the app venv, CM_BACKUP_TEST_URL and tools on PATH.
Test databases and encrypted evidence remain under .local; nothing is dropped.
"""

import os
import subprocess
import sys
import time
import unittest
import uuid
from pathlib import Path

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

ROOT = Path(__file__).resolve().parents[1]


class BackupCLI(unittest.TestCase):
    def test_encrypted_backup_restores_into_independent_database(self):
        admin_url = os.environ["CM_BACKUP_TEST_URL"]
        params = conninfo_to_dict(admin_url)
        self.assertIn(params["host"], ("127.0.0.1", "localhost"))
        suffix = uuid.uuid4().hex[:12]
        source = "cm_backup_test_" + suffix
        target = "cm_restore_" + suffix
        with psycopg.connect(admin_url, autocommit=True) as conn:
            for name in (source, target):
                conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        source_url = make_conninfo(admin_url, dbname=source)
        target_url = make_conninfo(admin_url, dbname=target)
        with psycopg.connect(source_url) as conn:
            conn.execute("CREATE TABLE proof (name text, points integer)")
            conn.execute("INSERT INTO proof VALUES ('restore evidence', 37)")
        folder = ROOT / ".local" / ("backup-test-" + suffix)
        folder.mkdir()
        identity = folder / "identity.txt"
        generated = subprocess.run(
            ["age-keygen", "-o", str(identity)], capture_output=True, check=True
        )
        self.assertEqual(generated.returncode, 0)
        recipient = subprocess.check_output(["age-keygen", "-y", str(identity)], text=True).strip()
        archive = folder / "test.dump.age"
        app_env = {
            **os.environ,
            "DATABASE_URL": "",
            "CM_DEBUG": "1",
            "PGHOST": params["host"],
            "PGPORT": params.get("port", "5432"),
            "PGUSER": params["user"],
            "PGPASSWORD": params.get("password", ""),
            "PGDATABASE": source,
            "CM_ALLOWED_HOSTS": "testserver,localhost",
        }
        evidence = folder / "fake-demo.json"
        prepared = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "backup_app_probe.py"), "seed", str(evidence)],
            env=app_env,
            capture_output=True,
            text=True,
        )
        self.assertEqual(prepared.returncode, 0, prepared.stderr)
        env = {
            **os.environ,
            "CM_BACKUP_DATABASE_URL": source_url,
            "CM_BACKUP_RECIPIENT": recipient,
            "CM_RESTORE_DATABASE_URL": target_url,
        }

        def cli(*args):
            return subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "backup.py"), *args],
                env=env,
                capture_output=True,
                text=True,
            )

        result = cli("backup", "--output", str(archive))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(archive.read_bytes().startswith(b"age-encryption.org/v1"))
        self.assertNotIn(b"restore evidence", archive.read_bytes())
        original = archive.read_bytes()
        result = cli("backup", "--output", str(archive))
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(archive.read_bytes(), original)
        result = cli(
            "restore",
            "--input",
            str(archive),
            "--identity",
            str(identity),
            "--target-db",
            "production",
        )
        self.assertNotEqual(result.returncode, 0)
        result = cli(
            "restore",
            "--input",
            str(archive),
            "--identity",
            str(identity),
            "--target-db",
            "cm_restore_wrong",
        )
        self.assertNotEqual(result.returncode, 0)
        corrupted = folder / "corrupt.dump.age"
        corrupted.write_bytes(original[:-20])
        result = cli(
            "restore", "--input", str(corrupted), "--identity", str(identity), "--target-db", target
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Decryption failed", result.stderr)
        with psycopg.connect(target_url) as conn:
            self.assertIsNone(conn.execute("SELECT to_regclass('proof')").fetchone()[0])
        restore_started = time.monotonic()
        result = cli(
            "restore", "--input", str(archive), "--identity", str(identity), "--target-db", target
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        print(f"Independent restore completed in {time.monotonic() - restore_started:.3f}s")
        with psycopg.connect(target_url) as conn:
            self.assertEqual(
                conn.execute("SELECT * FROM proof").fetchall(), [("restore evidence", 37)]
            )
        result = cli(
            "restore", "--input", str(archive), "--identity", str(identity), "--target-db", target
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not empty", result.stderr)
        app_env["PGDATABASE"] = target
        checked = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "backup_app_probe.py"), "check", str(evidence)],
            env=app_env,
            capture_output=True,
            text=True,
        )
        self.assertEqual(checked.returncode, 0, checked.stderr)
        env["CM_BACKUP_DATABASE_URL"] = (
            "postgresql://cm:do-not-print-this-password@127.0.0.1:55432/" + source
        )
        failed = folder / "failed.dump.age"
        result = cli("backup", "--output", str(failed))
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(failed.exists())
        self.assertNotIn("do-not-print-this-password", result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
