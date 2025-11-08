"""
Database utilities and engine initialization.
"""
import os
from sqlmodel import create_engine, SQLModel, Session, select
from sqlalchemy import text
from typing import Generator

from models import Book, Image, Export, Setting, Token, FTSBook, create_fts_table, create_fts_triggers

# Database file path
DATABASE_URL = "sqlite:///data/books.db"

# Create engine with proper settings for SQLite
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},  # Needed for SQLite
    echo=False  # Set to True for SQL debugging
)


def create_db_and_tables():
    """Create database and all tables"""
    # Ensure data directory exists
    os.makedirs("data", exist_ok=True)
    
    # Create main tables
    SQLModel.metadata.create_all(engine)
    
    # Create FTS table and triggers
    with Session(engine) as session:
        # Create FTS table
        session.exec(create_fts_table())
        
        # Create triggers
        for trigger in create_fts_triggers():
            try:
                session.exec(trigger)
            except Exception as e:
                # Triggers might already exist, which is fine
                print(f"Trigger creation note: {e}")
        
        session.commit()


def get_session() -> Generator[Session, None, None]:
    """Get database session"""
    with Session(engine) as session:
        yield session


def init_default_settings():
    """Initialize default settings if they don't exist"""
    with Session(engine) as session:
        # Check if policy defaults exist
        existing = session.exec(select(Setting).where(Setting.key == "policy_defaults")).first()
        
        if not existing:
            default_policies = {
                "payment_policy_name": "Immediate Payment Required",
                "shipping_policy_name": "Standard Shipping",
                "return_policy_name": "No Returns"
            }
            
            setting = Setting(key="policy_defaults", value=default_policies)
            session.add(setting)
            session.commit()
            print("Initialized default policy settings")


# Search functionality
def search_books(query: str, limit: int = 50) -> list[str]:
    """Search books using FTS5"""
    with Session(engine) as session:
        # Use FTS5 to search
        fts_query = text("""
            SELECT book_id FROM fts_books 
            WHERE fts_books MATCH :query
            LIMIT :limit
        """)
        
        results = session.exec(fts_query, {"query": query, "limit": limit}).fetchall()
        return [row[0] for row in results]


def get_book_with_images(book_id: str) -> Book | None:
    """Get a book with its images"""
    with Session(engine) as session:
        statement = select(Book).where(Book.id == book_id)
        book = session.exec(statement).first()
        return book
