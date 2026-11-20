"""
Unit tests for the destructive-test-fixture safety guard
(app/core/test_db_safety.py). These are pure URL-parsing/comparison checks -
no database connection is opened, so they run instantly and prove the guard
rejects an unsafe configuration *before* anything destructive could ever be
attempted, independent of whether a real database happens to be reachable.
"""

import pytest

from app.core.test_db_safety import UnsafeTestDatabaseError, assert_safe_test_database

DEV_URL = "postgresql+asyncpg://cynvexa:cynvexa@db:5432/cynvexa"
GOOD_TEST_URL = "postgresql+asyncpg://cynvexa:cynvexa@db:5432/cynvexa_test"


def test_accepts_a_properly_named_dedicated_test_database():
    # Must not raise.
    assert_safe_test_database(GOOD_TEST_URL, DEV_URL)


def test_rejects_missing_test_database_url():
    with pytest.raises(UnsafeTestDatabaseError, match="not set"):
        assert_safe_test_database(None, DEV_URL)


def test_rejects_empty_test_database_url():
    with pytest.raises(UnsafeTestDatabaseError, match="not set"):
        assert_safe_test_database("   ", DEV_URL)


def test_rejects_the_development_database_itself():
    # DEV_URL's own database name ("cynvexa") doesn't contain "test" at
    # all, so passing it as the test URL is correctly rejected by the
    # name-marker check before the same-as-dev check is even reached -
    # defense in depth, not a weaker guarantee. Asserting that here
    # directly, then exercising the same-as-dev branch in isolation below
    # with a "development" value that does happen to be named like a test
    # database, so that specific comparison is actually reachable.
    with pytest.raises(UnsafeTestDatabaseError, match="does not contain"):
        assert_safe_test_database(DEV_URL, DEV_URL)


def test_rejects_a_test_url_identical_to_the_given_development_url():
    with pytest.raises(UnsafeTestDatabaseError, match="same host, port and database"):
        assert_safe_test_database(GOOD_TEST_URL, GOOD_TEST_URL)


def test_rejects_a_database_not_named_as_a_test_database():
    not_named_test = "postgresql+asyncpg://cynvexa:cynvexa@db:5432/cynvexa_staging"
    with pytest.raises(UnsafeTestDatabaseError, match="does not contain"):
        assert_safe_test_database(not_named_test, DEV_URL)


@pytest.mark.parametrize(
    "production_like_url",
    [
        "postgresql+asyncpg://user:pw@ep-cool-river-123.us-east-2.aws.neon.tech/cynvexa_test",
        "postgresql+asyncpg://user:pw@mydb.render.com/cynvexa_test",
        "postgresql+asyncpg://user:pw@mydb.abcdefg.us-east-1.rds.amazonaws.com/cynvexa_test",
    ],
)
def test_rejects_a_production_like_host_even_if_the_database_name_says_test(production_like_url):
    with pytest.raises(UnsafeTestDatabaseError, match="production database host"):
        assert_safe_test_database(production_like_url, DEV_URL)


def test_rejects_a_test_url_that_differs_only_by_scheme_or_credentials_but_resolves_to_the_same_host_port_db():
    # Same host/port/db as the given "development" value, different driver
    # scheme and credentials - the guard compares host/port/db, not the
    # whole string, so this must still be rejected (a careless "just change
    # the driver" edit must not bypass the guard). Uses a test-named
    # "development" value so the name-marker check doesn't short-circuit
    # before this comparison is reached.
    same_target_different_credentials = "postgresql+psycopg://someone_else:pw@db:5432/cynvexa_test"
    with pytest.raises(UnsafeTestDatabaseError, match="same host, port and database"):
        assert_safe_test_database(same_target_different_credentials, GOOD_TEST_URL)
