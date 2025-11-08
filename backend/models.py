from datetime import datetime
from typing import Optional, Dict, Any, List
from uuid import uuid4
from sqlmodel import SQLModel, Field, Relationship, JSON, Column
from sqlalchemy import text
from enum import Enum


class BookStatus(str, Enum):
    NEW = "new"
    AUTO = "auto"
    NEEDS_REVIEW = "needs_review"
    APPROVED = "approved"
    EXPORTED = "exported"


class ConditionGrade(str, Enum):
    BRAND_NEW = "Brand New"
    LIKE_NEW = "Like New"
    VERY_GOOD = "Very Good"
    GOOD = "Good"
    ACCEPTABLE = "Acceptable"


class Book(SQLModel, table=True):
    __tablename__ = "books"
    
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    status: BookStatus = Field(default=BookStatus.NEW)
    
    # Core metadata
    title: Optional[str] = Field(default=None)
    author: Optional[str] = Field(default=None)
    publisher: Optional[str] = Field(default=None)
    year: Optional[str] = Field(default=None)
    language: Optional[str] = Field(default=None)
    format: Optional[str] = Field(default=None)
    edition: Optional[str] = Field(default=None)
    isbn13: Optional[str] = Field(default=None, unique=True)
    
    # Condition and pricing
    condition_grade: ConditionGrade = Field(default=ConditionGrade.GOOD)
    defects: Optional[str] = Field(default=None)
    price_suggested: Optional[float] = Field(default=None)
    price_min: Optional[float] = Field(default=None)
    price_max: Optional[float] = Field(default=None)
    quantity: int = Field(default=1)
    
    # AI-generated content
    title_ai: Optional[str] = Field(default=None)
    description_ai: Optional[str] = Field(default=None)
    specifics_ai: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSON))
    ai_validation_errors: List[str] = Field(default_factory=list, sa_column=Column(JSON))
    
    # Book type/category for eBay listing
    book_type: Optional[str] = Field(default=None)  # "nonfiction", "fiction", "childrens", or None
    
    # Timestamps
    created_at: int = Field(default_factory=lambda: int(datetime.now().timestamp() * 1000))
    updated_at: int = Field(default_factory=lambda: int(datetime.now().timestamp() * 1000))
    
    # Export and verification
    verified: bool = Field(default=False)
    
    # eBay publishing
    sku: Optional[str] = Field(default=None)
    ebay_category_id: Optional[str] = Field(default=None)  # Selected eBay leaf category ID
    ebay_offer_id: Optional[str] = Field(default=None)
    ebay_listing_id: Optional[str] = Field(default=None)
    publish_status: Optional[str] = Field(default=None)  # e.g., "published", "failed", "pending"
    
    # Relationships
    images: list["Image"] = Relationship(back_populates="book")


class Image(SQLModel, table=True):
    __tablename__ = "images"
    
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    book_id: str = Field(foreign_key="books.id")
    path: str = Field()
    width: int = Field()
    height: int = Field()
    hash: Optional[str] = Field(default=None)
    
    # Relationship
    book: Book = Relationship(back_populates="images")


class Export(SQLModel, table=True):
    __tablename__ = "exports"
    
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    created_at: int = Field(default_factory=lambda: int(datetime.now().timestamp() * 1000))
    file_path: str = Field()
    row_count: int = Field()


class Setting(SQLModel, table=True):
    __tablename__ = "settings"
    
    key: str = Field(primary_key=True)
    value: Optional[Dict[str, Any]] = Field(default=None, sa_type=JSON)


class Token(SQLModel, table=True):
    """OAuth token storage for eBay API access"""
    __tablename__ = "tokens"
    
    provider: str = Field(primary_key=True, default="ebay")  # "ebay"
    access_token: str = Field()  # Encrypted in storage
    refresh_token: str = Field()  # Encrypted in storage
    expires_at: int = Field()  # Unix timestamp (milliseconds)
    token_type: str = Field(default="Bearer")
    scope: Optional[str] = Field(default=None)  # OAuth scopes granted
    created_at: int = Field(default_factory=lambda: int(datetime.now().timestamp() * 1000))
    updated_at: int = Field(default_factory=lambda: int(datetime.now().timestamp() * 1000))


# FTS5 Virtual Table for full-text search
class FTSBook(SQLModel, table=True):
    __tablename__ = "fts_books"
    __table_args__ = {"sqlite_with_rowid": False}
    
    book_id: str = Field(primary_key=True)
    title: Optional[str] = Field(default=None)
    author: Optional[str] = Field(default=None)
    isbn13: Optional[str] = Field(default=None)


# Database initialization
def create_fts_table():
    """Create the FTS5 virtual table"""
    return text("""
    CREATE VIRTUAL TABLE IF NOT EXISTS fts_books USING fts5(
        book_id UNINDEXED,
        title,
        author,
        isbn13,
        content='books',
        content_rowid='rowid'
    )
    """)


def create_fts_triggers():
    """Create triggers to keep FTS table in sync"""
    triggers = [
        """
        CREATE TRIGGER IF NOT EXISTS books_ai AFTER INSERT ON books BEGIN
            INSERT INTO fts_books(book_id, title, author, isbn13)
            VALUES (new.id, new.title, new.author, new.isbn13);
        END
        """,
        """
        CREATE TRIGGER IF NOT EXISTS books_ad AFTER DELETE ON books BEGIN
            DELETE FROM fts_books WHERE book_id = old.id;
        END
        """,
        """
        CREATE TRIGGER IF NOT EXISTS books_au AFTER UPDATE ON books BEGIN
            DELETE FROM fts_books WHERE book_id = old.id;
            INSERT INTO fts_books(book_id, title, author, isbn13)
            VALUES (new.id, new.title, new.author, new.isbn13);
        END
        """
    ]
    return [text(trigger) for trigger in triggers]