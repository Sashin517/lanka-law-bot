"""Database infrastructure.

``session`` owns the legacy synchronous SQLite metadata store, while
``postgres_session`` owns async research-chat persistence. Keeping the bases
separate prevents accidental cross-database foreign keys or migrations.
"""
