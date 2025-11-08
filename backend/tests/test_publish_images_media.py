"""
Tests for eBay publish flow with Media API image upload
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import HTTPException

from models import Book, Image, ConditionGrade, BookStatus
from integrations.ebay.publish import prepare_for_publish
from integrations.ebay.images import resolve_listing_urls
from integrations.ebay.media_api import MediaAPIError


class TestPublishImagesMedia:
    """Test publish flow with Media API image upload"""
    
    @pytest.fixture
    def mock_book(self):
        """Create a mock book with images"""
        book = Book(
            id="test-book-id",
            title="Test Book",
            title_ai="Test Book Title",
            description_ai="Test description",
            status=BookStatus.APPROVED,
            condition_grade=ConditionGrade.GOOD,
            price_suggested=19.99,
            quantity=1,
            publisher="Test Publisher"
        )
        book.images = [
            Image(id="img1", book_id="test-book-id", path="img1.jpg", width=1600, height=1200),
            Image(id="img2", book_id="test-book-id", path="img2.jpg", width=1600, height=1200),
        ]
        return book
    
    @pytest.fixture
    def mock_session(self, mock_book):
        """Mock database session"""
        session = MagicMock()
        session.get.return_value = mock_book
        return session
    
    @pytest.fixture
    def mock_token(self):
        """Mock OAuth token"""
        return "mock_access_token"
    
    @pytest.mark.asyncio
    async def test_prepare_for_publish_success(self, mock_book, mock_session, mock_token):
        """Test successful publish preparation with image upload"""
        eps_urls = [
            "https://i.ebayimg.com/images/g/img1.jpg",
            "https://i.ebayimg.com/images/g/img2.jpg"
        ]
        
        with patch('integrations.ebay.publish.resolve_listing_urls') as mock_resolve:
            mock_resolve.return_value = eps_urls
            
            result = await prepare_for_publish(
                book_id="test-book-id",
                token=mock_token,
                session=mock_session,
                payment_policy_id="PAY123",
                return_policy_id="RET123",
                fulfillment_policy_id="FUL123"
            )
            
            assert "inventory_item" in result
            assert "image_urls" in result
            assert result["image_urls"] == eps_urls
            
            # Verify inventory item has image URLs
            inventory_item = result["inventory_item"]
            product = inventory_item["product"]
            assert "imageUrls" in product
            assert product["imageUrls"] == eps_urls
            
            # Verify image URLs are in inventory item
            assert len(product["imageUrls"]) == 2
            assert all(url.startswith('https://') for url in product["imageUrls"])
            
            mock_resolve.assert_called_once_with(
                book_id="test-book-id",
                token=mock_token,
                session=mock_session,
                base_url=None
            )
    
    @pytest.mark.asyncio
    async def test_prepare_for_publish_no_images(self, mock_session, mock_token):
        """Test that missing images raises HTTPException"""
        book = Book(
            id="test-book-id",
            title="Test Book",
            status=BookStatus.APPROVED
        )
        book.images = []
        mock_session.get.return_value = book
        
        with patch('integrations.ebay.publish.resolve_listing_urls') as mock_resolve:
            mock_resolve.side_effect = ValueError("Book test-book-id has no images")
            
            with pytest.raises(HTTPException) as exc_info:
                await prepare_for_publish(
                    book_id="test-book-id",
                    token=mock_token,
                    session=mock_session
                )
            
            assert exc_info.value.status_code == 400
            assert "Image resolution failed" in str(exc_info.value.detail)
    
    @pytest.mark.asyncio
    async def test_prepare_for_publish_empty_image_urls(self, mock_book, mock_session, mock_token):
        """Test that empty image URLs raises HTTPException"""
        with patch('integrations.ebay.publish.resolve_listing_urls') as mock_resolve:
            mock_resolve.return_value = []
            
            with pytest.raises(HTTPException) as exc_info:
                await prepare_for_publish(
                    book_id="test-book-id",
                    token=mock_token,
                    session=mock_session
                )
            
            assert exc_info.value.status_code == 400
            assert "No valid image URLs" in str(exc_info.value.detail)
    
    @pytest.mark.asyncio
    async def test_prepare_for_publish_invalid_http_url(self, mock_book, mock_session, mock_token):
        """Test that HTTP URLs (non-HTTPS) raises HTTPException"""
        invalid_urls = [
            "http://i.ebayimg.com/images/g/img1.jpg",  # HTTP instead of HTTPS
            "https://i.ebayimg.com/images/g/img2.jpg"
        ]
        
        with patch('integrations.ebay.publish.resolve_listing_urls') as mock_resolve:
            mock_resolve.return_value = invalid_urls
            
            with pytest.raises(HTTPException) as exc_info:
                await prepare_for_publish(
                    book_id="test-book-id",
                    token=mock_token,
                    session=mock_session
                )
            
            assert exc_info.value.status_code == 400
            assert "must be HTTPS" in str(exc_info.value.detail)
    
    @pytest.mark.asyncio
    async def test_prepare_for_publish_media_api_error(self, mock_book, mock_session, mock_token):
        """Test that Media API errors are handled"""
        with patch('integrations.ebay.publish.resolve_listing_urls') as mock_resolve:
            mock_resolve.side_effect = MediaAPIError("Upload failed: Server error")
            
            with pytest.raises(HTTPException) as exc_info:
                await prepare_for_publish(
                    book_id="test-book-id",
                    token=mock_token,
                    session=mock_session
                )
            
            assert exc_info.value.status_code == 500
            assert "Image resolution error" in str(exc_info.value.detail)
    
    @pytest.mark.asyncio
    async def test_prepare_for_publish_book_not_found(self, mock_session, mock_token):
        """Test that missing book raises HTTPException"""
        mock_session.get.return_value = None
        
        with pytest.raises(HTTPException) as exc_info:
            await prepare_for_publish(
                book_id="nonexistent",
                token=mock_token,
                session=mock_session
            )
        
        assert exc_info.value.status_code == 404
        assert "not found" in str(exc_info.value.detail).lower()
    
    @pytest.mark.asyncio
    async def test_prepare_for_publish_validates_all_https(self, mock_book, mock_session, mock_token):
        """Test that all image URLs must be HTTPS"""
        eps_urls = [
            "https://i.ebayimg.com/images/g/img1.jpg",
            "https://i.ebayimg.com/images/g/img2.jpg",
            "https://i.ebayimg.com/images/g/img3.jpg"
        ]
        
        with patch('integrations.ebay.publish.resolve_listing_urls') as mock_resolve:
            mock_resolve.return_value = eps_urls
            
            result = await prepare_for_publish(
                book_id="test-book-id",
                token=mock_token,
                session=mock_session
            )
            
            # All URLs should be HTTPS
            for url in result["image_urls"]:
                assert url.startswith('https://')
            
            # Inventory item should have all URLs
            inventory_item = result["inventory_item"]
            product = inventory_item["product"]
            assert len(product["imageUrls"]) == 3
            assert all(url.startswith('https://') for url in product["imageUrls"])

