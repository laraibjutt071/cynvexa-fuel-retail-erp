"""
Guards against ever running a destructive schema operation (DROP SCHEMA,
TRUNCATE, etc.) against anything other than a database that is unambiguously
a dedicated, throwaway test database.

Background: before this module existed, the pytest suite's schema-reset
fixture connected to whatever DATABASE_URL happened to be configured - which,
in this project's Docker Compose setup, is always the real local development
database. A pytest run's DROP SCHEMA PUBLIC CASCADE therefore wiped the dev
database's data and its Alembic migration history more than once (see
docs/TEST_DATABASE_ISOLATION_REPORT.md for the incident history). This is
the hard guard that makes that structurally impossible going forward - never
rely on documentation or developer discipline alone for a destructive
operation.

This module performs no I/O and opens no connections - it only parses and
compares connection URLs, so it is cheap and safe to call before every
single destructive operation, not just once at process startup.
"""

from urllib.parse import urlsplit

# Hostname substrings that indicate a managed cloud database - this
# project's production deployment uses Neon; the others are included
# defensively in case this guard is ever reused in another project or this
# one grows a second environment. A destructive test fixture must never be
# able to reach any of these, regardless of what else is misconfigured.
_PRODUCTION_HOST_MARKERS = (
    "neon.tech",
    ".neon.database",
    "render.com",
    "amazonaws.com",
    ".rds.",
)

# A test database's name must contain this - "cynvexa_test" by convention
# in this project. This is deliberately strict: a database merely named
# differently from the dev database (e.g. a typo) is not enough to prove
# intent; the name must affirmatively say "test".
_REQUIRED_TEST_DB_NAME_MARKER = "test"


class UnsafeTestDatabaseError(RuntimeError):
    """Raised when a destructive test operation's target database cannot be
    proven safe. Always raised before any DDL runs - never after."""


def _split(url: str) -> tuple[str, str, int | None]:
    parsed = urlsplit(url)
    host = (parsed.hostname or "").lower()
    dbname = (parsed.path or "").lstrip("/").lower()
    return host, dbname, parsed.port


def assert_safe_test_database(test_database_url: str | None, development_database_url: str) -> None:
    """Raises UnsafeTestDatabaseError unless `test_database_url` is
    unambiguously a dedicated, non-production, non-development test
    database. Must be called immediately before any destructive schema
    operation, with the real values actually in use - never with a cached
    or assumed value.
    """
    if not test_database_url or not test_database_url.strip():
        raise UnsafeTestDatabaseError(
            "TEST_DATABASE_URL is not set. Destructive test fixtures refuse to run without an "
            "explicit, dedicated test database - see docs/TEST_DATABASE_ISOLATION_REPORT.md."
        )

    test_host, test_db, test_port = _split(test_database_url)

    for marker in _PRODUCTION_HOST_MARKERS:
        if marker in test_host:
            raise UnsafeTestDatabaseError(
                f"TEST_DATABASE_URL host '{test_host}' looks like a managed cloud/production database "
                f"host (matched '{marker}'). Refusing to run destructive operations against it."
            )

    if _REQUIRED_TEST_DB_NAME_MARKER not in test_db:
        raise UnsafeTestDatabaseError(
            f"TEST_DATABASE_URL database name '{test_db}' does not contain "
            f"'{_REQUIRED_TEST_DB_NAME_MARKER}'. Destructive fixtures require an explicitly-named "
            "test database so a misconfigured URL can never be mistaken for one."
        )

    dev_host, dev_db, dev_port = _split(development_database_url)
    if (test_host, test_db, test_port) == (dev_host, dev_db, dev_port):
        raise UnsafeTestDatabaseError(
            "TEST_DATABASE_URL resolves to the exact same host, port and database name as the "
            "development DATABASE_URL. Refusing to run destructive operations against it."
        )
