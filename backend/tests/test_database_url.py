from app.db.url import normalize_database_url


def test_postgresql_url_uses_psycopg_driver() -> None:
    assert normalize_database_url("postgresql://user:password@localhost/database") == (
        "postgresql+psycopg://user:password@localhost/database"
    )


def test_explicit_psycopg_url_is_unchanged() -> None:
    database_url = "postgresql+psycopg://user:password@localhost/database"
    assert normalize_database_url(database_url) == database_url
