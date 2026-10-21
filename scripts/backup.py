"""Encrypted PostgreSQL backups. Credentials are accepted only via environment."""

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import psycopg
from psycopg.conninfo import conninfo_to_dict


class BackupError(Exception):
    pass


def required(name):
    value = os.environ.get(name, "").strip()
    if not value:
        raise BackupError("Missing setting: " + name)
    return value


def pg_environment(connection):
    names = {
        "host": "PGHOST",
        "hostaddr": "PGHOSTADDR",
        "port": "PGPORT",
        "dbname": "PGDATABASE",
        "user": "PGUSER",
        "password": "PGPASSWORD",
        "sslmode": "PGSSLMODE",
        "sslrootcert": "PGSSLROOTCERT",
        "sslcert": "PGSSLCERT",
        "sslkey": "PGSSLKEY",
        "options": "PGOPTIONS",
        "channel_binding": "PGCHANNELBINDING",
        "connect_timeout": "PGCONNECT_TIMEOUT",
    }
    params = conninfo_to_dict(connection)
    if params.keys() - names.keys():
        raise BackupError("Unsupported PostgreSQL connection option.")
    env = {key: value for key, value in os.environ.items() if not key.startswith("PG")}
    return {
        **env,
        **{names[key]: value for key, value in params.items()},
        "PGCONNECT_TIMEOUT": "15",
    }


def backup(args):
    connection = required("CM_BACKUP_DATABASE_URL")
    recipient = required("CM_BACKUP_RECIPIENT")
    # Exclusive creation protects an existing backup, including from reruns.
    with Path(args.output).open("xb") as encrypted:
        try:
            with subprocess.Popen(
                [
                    "pg_dump",
                    "--format=custom",
                    "--compress=6",
                    "--no-owner",
                    "--no-acl",
                    "--no-password",
                ],
                env=pg_environment(connection),
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            ) as dump:
                try:
                    result = subprocess.run(
                        ["age", "-r", recipient],
                        stdin=dump.stdout,
                        stdout=encrypted,
                        stderr=subprocess.DEVNULL,
                        timeout=600,
                    )
                except BaseException:
                    dump.kill()
                    raise
                finally:
                    dump.stdout.close()
                code = dump.wait(timeout=30)
                if result.returncode or code:
                    raise BackupError("Export or encryption failed; output is incomplete.")
        except Exception:
            # Only this newly-created file; no directory or bulk cleanup.
            encrypted.close()
            Path(args.output).unlink()
            raise
    print("Encrypted backup created.")


def restore(args):
    connection = required("CM_RESTORE_DATABASE_URL")
    if not args.target_db.startswith("cm_restore_"):
        raise BackupError("Restore database name must start with cm_restore_.")
    with psycopg.connect(connection, connect_timeout=15) as conn:
        actual = conn.execute("SELECT current_database()").fetchone()[0]
        if actual != args.target_db:
            raise BackupError("Restore target does not match --target-db.")
        populated = conn.execute(
            "SELECT EXISTS (SELECT 1 FROM pg_class c JOIN pg_namespace n "
            "ON n.oid=c.relnamespace WHERE n.nspname NOT LIKE 'pg_%' "
            "AND n.nspname <> 'information_schema')"
        ).fetchone()[0]
        if populated:
            raise BackupError("Restore target is not empty.")
    # Fully authenticate/decrypt before allowing pg_restore to execute SQL.
    with tempfile.NamedTemporaryFile(prefix="cm-restore-", suffix=".dump", delete=False) as tmp:
        plain = Path(tmp.name)
    try:
        with plain.open("wb") as output:
            result = subprocess.run(
                ["age", "--decrypt", "-i", args.identity, args.input],
                stdout=output,
                stderr=subprocess.DEVNULL,
                timeout=600,
            )
        if result.returncode:
            raise BackupError("Decryption failed; target was not changed.")
        result = subprocess.run(
            [
                "pg_restore",
                "--dbname",
                args.target_db,
                "--single-transaction",
                "--exit-on-error",
                "--no-owner",
                "--no-acl",
                "--no-password",
                str(plain),
            ],
            env=pg_environment(connection),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=600,
        )
        if result.returncode:
            raise BackupError("Restore failed; transaction rolled back.")
    finally:
        plain.unlink()
    print("Restore completed. Verify application data and login before use.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    export = commands.add_parser("backup")
    export.add_argument("--output", required=True)
    recover = commands.add_parser("restore")
    recover.add_argument("--input", required=True)
    recover.add_argument("--identity", required=True)
    recover.add_argument("--target-db", required=True)
    args = parser.parse_args()
    try:
        {"backup": backup, "restore": restore}[args.command](args)
    except BackupError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except Exception:
        # Provider and subprocess exceptions can contain URLs/passwords or SQL.
        print(
            "Backup operation failed. Check settings, tools and connectivity privately.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
