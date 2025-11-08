"""
Database migration utilities for ensuring schema consistency.
Adds missing AI columns to existing database tables.
"""
from typing import Set
from sqlmodel import Session
from sqlalchemy import text, Engine
import logging

logger = logging.getLogger(__name__)

REQUIRED_COLUMNS = {
    "title_ai": "TEXT",
    "description_ai": "TEXT",
    "specifics_ai": "JSON",
    "ai_validation_errors": "JSON",
    "book_type": "TEXT",
    "ebay_category_id": "TEXT",
}


def _existing_columns(session: Session) -> Set[str]:
    """Get set of existing column names from books table."""
    rows = session.exec(text("PRAGMA table_info('books')")).all()
    return {row[1] for row in rows}  # row[1] = name column


def _safe_type(sqltype: str) -> str:
    """SQLite accepts JSON, but fallback to TEXT for older builds if needed."""
    # SQLite 3.38+ supports JSON type natively
    # For compatibility, we'll use JSON (SQLite will handle it)
    return sqltype if sqltype != "JSON" else "JSON"


def ensure_schema(engine: Engine) -> None:
    """
    Ensure all required AI columns exist in the books table.
    Adds missing columns if they don't exist (idempotent).
    """
    try:
        with Session(engine) as session:
            cols = _existing_columns(session)
            added = []
            
            for name, sqltype in REQUIRED_COLUMNS.items():
                if name not in cols:
                    try:
                        safe_type = _safe_type(sqltype)
                        session.exec(text(f"ALTER TABLE books ADD COLUMN {name} {safe_type}"))
                        added.append(name)
                        logger.info(f"Added missing column: {name} ({safe_type})")
                    except Exception as e:
                        logger.error(f"Failed to add column {name}: {e}")
                        # Rollback on error
                        session.rollback()
                        raise
            
            if added:
                session.commit()
                logger.info(f"Schema migration completed. Added columns: {', '.join(added)}")
            else:
                logger.debug("Schema already up to date. No columns added.")
                
    except Exception as e:
        logger.error(f"Schema migration failed: {e}", exc_info=True)
        raise

