def normalize_database_url(database_url: str) -> str:
    """Use Psycopg 3 when a PostgreSQL URL omits its driver."""

    if database_url.startswith("postgres://"):
        return f"postgresql+psycopg://{database_url.removeprefix('postgres://')}"
    if database_url.startswith("postgresql://"):
        return f"postgresql+psycopg://{database_url.removeprefix('postgresql://')}"
    return database_url
