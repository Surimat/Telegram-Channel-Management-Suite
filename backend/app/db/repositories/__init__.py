"""Repositories: the only place that talks to the database.

Business logic depends on repositories, not on SQLAlchemy sessions directly.
This keeps SQL portable (SQLite -> PostgreSQL) without touching services.
"""
