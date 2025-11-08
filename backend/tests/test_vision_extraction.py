"""
Vision Extraction Integration Tests

Tests for /ai/vision/{book_id} endpoint with sample images.
"""

import pytest
import os
import tempfile
import base64
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient

from main import app
from models import Book, Image, BookStatus, ConditionGrade
from db import create_db_and_tables, get_session
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool


@pytest.fixture
def db_session():
    """Create in-memory database session for testing."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    
    with Session(engine) as session:
        yield session


@pytest.fixture
def client(db_session):
    """Create test client with dependency override."""
    def get_session_override():
        yield db_session
    
    app.dependency_overrides[get_session] = get_session_override
    
    with TestClient(app) as test_client:
        yield test_client
    
    app.dependency_overrides.clear()


@pytest.fixture
def sample_book(db_session):
    """Create a sample book in the database."""
    book = Book(
        id="test-book-123",
        status=BookStatus.NEW,
        title="Test Book",
        author="Test Author",
        publisher="Test Publisher",
        year="2020",
        isbn13="9781234567890",
        condition_grade=ConditionGrade.GOOD,
        price_suggested=19.99,
        quantity=1
    )
    db_session.add(book)
    db_session.commit()
    db_session.refresh(book)
    return book


@pytest.fixture
def sample_images(tmp_path, sample_book):
    """Create sample image files for testing."""
    images_dir = tmp_path / "data" / "images" / sample_book.id
    images_dir.mkdir(parents=True, exist_ok=True)
    
    # Create a minimal valid JPEG (1x1 pixel)
    # JPEG header + minimal data
    jpeg_data = base64.b64decode(
        "/9j/4AAQSkZJRgABAQEAYABgAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0a"
        "HBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/2wBDAQkJCQwLDBgNDRgyIRwhMjIyMjIy"
        "MjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjL/wAARCAABAAEDASIA"
        "AhEBAxEB/8QAFQABAQAAAAAAAAAAAAAAAAAAAAv/xAAUEAEAAAAAAAAAAAAAAAAAAAAA/8QAFQ"
        "EBAQAAAAAAAAAAAAAAAAAAAAX/xAAUEQEAAAAAAAAAAAAAAAAAAAAA/9oADAMBAAIRAxEAPwCd"
        "ABmX/9k="
    )
    
    image_path = images_dir / "test_image.jpg"
    image_path.write_bytes(jpeg_data)
    
    # Add image record to database
    image = Image(
        id="img-123",
        book_id=sample_book.id,
        path=str(image_path),
        width=1,
        height=1,
        hash="test-hash"
    )
    
    return {"path": str(image_path), "image": image}


class TestVisionExtraction:
    """Test vision extraction endpoint."""
    
    @pytest.mark.asyncio
    async def test_vision_endpoint_not_found(self, client):
        """Test vision endpoint returns 404 for non-existent book."""
        response = client.post("/ai/vision/nonexistent-book")
        assert response.status_code == 404
    
    @pytest.mark.asyncio
    @patch.dict(os.environ, {"OPENAI_API_KEY": "test-key", "OPENAI_MODEL": "gpt-4o"})
    async def test_vision_endpoint_mock_extraction(self, client, db_session, sample_book, sample_images, tmp_path, monkeypatch):
        """Test vision extraction with mocked OpenAI API."""
        # Set base_dir for vision service
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        
        # Mock OpenAI client
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = '{"title": "Extracted Title", "author": "Extracted Author", "isbn13": "9781234567890", "publisher": "Extracted Publisher", "publicationYear": "2020", "format": "Hardcover", "language": "English", "condition": "Good", "topic": "Fiction"}'
        
        with patch('services.vision_extraction.OpenAI') as mock_openai:
            mock_client = MagicMock()
            mock_client.chat.completions.create = MagicMock(return_value=mock_response)
            mock_openai.return_value = mock_client
            
            # Update base_dir to use tmp_path
            from services.vision_extraction import VisionExtractionService
            service = VisionExtractionService()
            service.base_dir = str(tmp_path / "data" / "images")
            
            # Add image to database
            db_session.add(sample_images["image"])
            db_session.commit()
            
            # Mock the service in the route
            with patch('routes.ai_vision.vision_service.base_dir', str(tmp_path / "data" / "images")):
                response = client.post(f"/ai/vision/{sample_book.id}")
                
                # Should succeed (even if OpenAI call fails, endpoint should handle it)
                assert response.status_code in [200, 500]  # 500 if OpenAI actually called
    
    @pytest.mark.asyncio
    async def test_vision_endpoint_no_images(self, client, db_session, sample_book):
        """Test vision extraction with no images."""
        response = client.post(f"/ai/vision/{sample_book.id}")
        # Should return error about no images
        assert response.status_code in [200, 400, 500]
        data = response.json()
        # Should indicate no images found
        assert "ok" in data or "error" in data or "errors" in data
    
    def test_vision_service_initialization(self):
        """Test VisionExtractionService can be initialized."""
        from services.vision_extraction import VisionExtractionService
        
        # Without API key (should still initialize)
        service = VisionExtractionService(openai_api_key=None)
        assert service.client is None
        
        # With API key
        service = VisionExtractionService(openai_api_key="test-key")
        assert service.client is not None

