"""Run the suite against isolated, ephemeral PostgreSQL databases only."""

import os
import subprocess
import sys

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict


def main() -> int:
    names = ("viradata_finance_test_a", "viradata_finance_test_b", "viradata_finance_test_api")
    options = conninfo_to_dict(os.environ["TEST_DATABASE_URL"])
    if options.get("host") != "127.0.0.1" or options.get("dbname") not in names:
        raise RuntimeError("Test runner requires dedicated local test databases")
    options["dbname"] = "postgres"
    with psycopg.connect(**options, autocommit=True) as conn:
        for name in names:
            if not conn.execute("SELECT 1 FROM pg_database WHERE datname=%s", (name,)).fetchone():
                conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    return subprocess.call([sys.executable, "-m", "pytest", "-q", "tests"])


if __name__ == "__main__":
    raise SystemExit(main())
