"""
Database utilities - compatibility shim for db package.
This file is kept for backward compatibility with existing imports.
All functionality has been moved to the db package.
"""
from db import (
    engine,
    get_session,
    create_db_and_tables,
    init_default_settings,
    search_books,
    get_book_with_images,
)

__all__ = [
    "engine",
    "get_session",
    "create_db_and_tables",
    "init_default_settings",
    "search_books",
    "get_book_with_images",
]
