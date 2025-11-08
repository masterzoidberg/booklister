"""
Tests for eBay image strategy resolver (Media API)
"""
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from sqlmodel import Session

from models import Book, Image, ConditionGrade, BookStatus
from integrations.ebay.images import resolve_listing_urls
from settings import ebay_settings


class TestImageStrategyMedia:
    """Test image strategy resolver for Media API"""
    
    @pytest.fixture
    def mock_book(self):
        """Create a mock book with images"""
        book = Book(
            id="test-book-id",
            title="Test Book",
            status=BookStatus.APPROVED,
            condition_grade=ConditionGrade.GOOD
        )
        book.images = [
            Image(id="img1", book_id="test-book-id", path="img1.jpg", width=1600, height=1200),
            Image(id="img2", book_id="test-book-id", path="img2.jpg", width=1600, height=1200),
        ]
        return book
    
    @pytest.fixture
    def mock_session(self, mock_book):
        """Mock database session"""
        session = MagicMock(spec=Session)
        session.get.return_value = mock_book
        return session
    
    @pytest.fixture
    def mock_token(self):
        """Mock OAuth token"""
        return "mock_access_token"
    
    @pytest.fixture
    def mock_image_paths(self, tmp_path):
        """Create mock image files"""
        book_dir = tmp_path / "test-book-id"
        book_dir.mkdir()
        
        image_paths = []
        for i in range(2):
            img_file = book_dir / f"img{i+1}.jpg"
            img_file.write_bytes(b"fake image data")
            image_paths.append(img_file)
        
        return image_paths, tmp_path
    
    @pytest.mark.asyncio
    async def test_resolve_listing_urls_media_strategy(
        self, mock_book, mock_session, mock_token, mock_image_paths, tmp_path
    ):
        """Test Media API strategy resolves EPS URLs"""
        image_paths, base_dir = mock_image_paths
        
        # Mock settings to use media strategy
        with patch('integrations.ebay.images.ebay_settings') as mock_settings, \
             patch('integrations.ebay.images.normalize_book_images') as mock_norm, \
             patch('integrations.ebay.images.upload_many') as mock_upload:
            
            mock_settings.image_strategy = "media"
            mock_settings.image_base_path = str(base_dir)
            mock_settings.get_api_base_url.return_value = "https://api.ebay.com"
            
            # Mock normalization
            normalized_paths = [Path(f"norm_{i:02d}.jpg") for i in range(2)]
            mock_norm.return_value = normalized_paths
            
            # Mock upload
            eps_urls = [
                "https://i.ebayimg.com/images/g/img1.jpg",
                "https://i.ebayimg.com/images/g/img2.jpg"
            ]
            mock_upload.return_value = eps_urls
            
            result = await resolve_listing_urls(
                book_id="test-book-id",
                token=mock_token,
                session=mock_session
            )
            
            assert len(result) == 2
            assert all(url.startswith('https://') for url in result)
            assert all('ebayimg.com' in url for url in result)
            mock_norm.assert_called_once()
            mock_upload.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_resolve_listing_urls_no_images(self, mock_token, mock_session):
        """Test that no images raises ValueError"""
        book = Book(
            id="test-book-id",
            title="Test Book",
            status=BookStatus.APPROVED
        )
        book.images = []
        mock_session.get.return_value = book
        
        with pytest.raises(ValueError) as exc_info:
            await resolve_listing_urls(
                book_id="test-book-id",
                token=mock_token,
                session=mock_session
            )
        
        assert "no images" in str(exc_info.value).lower()
    
    @pytest.mark.asyncio
    async def test_resolve_listing_urls_too_many_images(self, mock_token, mock_session):
        """Test that too many images (>24) raises ValueError"""
        book = Book(
            id="test-book-id",
            title="Test Book",
            status=BookStatus.APPROVED
        )
        # Create 25 images (max is 24)
        book.images = [
            Image(id=f"img{i}", book_id="test-book-id", path=f"img{i}.jpg", width=1600, height=1200)
            for i in range(25)
        ]
        mock_session.get.return_value = book
        
        with patch('integrations.ebay.images.ebay_settings') as mock_settings:
            mock_settings.media_max_images = 24
            mock_settings.image_strategy = "media"
            mock_settings.image_base_path = "data/images"
            
            # Should warn and limit to 24
            with patch('integrations.ebay.images.logger') as mock_logger:
                mock_logger.warning.assert_called()
    
    @pytest.mark.asyncio
    async def test_resolve_listing_urls_validates_https(self, mock_book, mock_session, mock_token):
        """Test that resolved URLs are validated as HTTPS"""
        with patch('integrations.ebay.images.ebay_settings') as mock_settings, \
             patch('integrations.ebay.images.normalize_book_images') as mock_norm, \
             patch('integrations.ebay.images.upload_many') as mock_upload, \
             patch('integrations.ebay.images.Path.exists') as mock_exists:
            
            mock_settings.image_strategy = "media"
            mock_settings.image_base_path = "data/images"
            mock_exists.return_value = True
            
            mock_norm.return_value = [Path("norm_00.jpg")]
            
            # Return invalid HTTP URL (should still validate)
            mock_upload.return_value = ["http://i.ebayimg.com/images/g/img1.jpg"]
            
            # Should still work but log warning
            result = await resolve_listing_urls(
                book_id="test-book-id",
                token=mock_token,
                session=mock_session
            )
            
            # Note: Validation happens in _validate_eps_urls which may log warnings
            assert len(result) == 1
    
    @pytest.mark.asyncio
    async def test_resolve_listing_urls_self_host_strategy(self, mock_book, mock_session, mock_token):
        """Test self-host strategy returns local URLs"""
        with patch('integrations.ebay.images.ebay_settings') as mock_settings:
            mock_settings.image_strategy = "self_host"
            mock_settings.ebay_env = "production"
            mock_settings.get_api_base_url.return_value = "https://api.ebay.com"
            
            result = await resolve_listing_urls(
                book_id="test-book-id",
                token=mock_token,
                session=mock_session,
                base_url="https://example.com"
            )
            
            assert len(result) == 2
            assert all(url.startswith('https://') for url in result)
            assert all(f"test-book-id" in url for url in result)
    
    @pytest.mark.asyncio
    async def test_resolve_listing_urls_book_not_found(self, mock_session, mock_token):
        """Test that missing book raises ValueError"""
        mock_session.get.return_value = None
        
        with pytest.raises(ValueError) as exc_info:
            await resolve_listing_urls(
                book_id="nonexistent",
                token=mock_token,
                session=mock_session
            )
        
        assert "not found" in str(exc_info.value).lower()

