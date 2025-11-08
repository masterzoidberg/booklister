"""
Mapping + Media API Integration Regression Tests

Tests for integration between mapping layer and Media API image URL resolution.
"""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from models import Book, Image, ConditionGrade

from integrations.ebay.mapping import (
    build_inventory_item,
    build_offer,
    build_mapping_result,
    MappingResult
)
from integrations.ebay.images import resolve_listing_urls


class MockImage:
    """Mock Image object for testing."""
    def __init__(self, path: str, width: int = 1600, height: int = 1200):
        self.path = path
        self.id = f"img-{path.split('/')[-1]}"
        self.book_id = "test-book"
        self.width = width
        self.height = height
        self.hash = "test-hash"


class TestMappingMediaIntegration:
    """Test integration between mapping and Media API."""
    
    @pytest.fixture
    def sample_book(self):
        """Create a sample book with all fields populated."""
        book = Book(
            id="test-book-integration",
            title="Integration Test Book",
            title_ai="Integration Test Book - AI Generated Title",
            description_ai="This is a detailed description for integration testing",
            author="Test Author",
            publisher="Test Publisher",
            year="2020",
            isbn13="9781234567890",
            edition="1st Edition",
            format="Hardcover",
            language="English",
            condition_grade=ConditionGrade.GOOD,
            price_suggested=19.99,
            quantity=1,
            specifics_ai={
                "topic": "Fiction",
                "genre": "Mystery",
                "signed": False,
                "inscribed": False
            }
        )
        
        # Add mock images
        book.images = [
            MockImage("data/images/test-book/image1.jpg"),
            MockImage("data/images/test-book/image2.jpg"),
            MockImage("data/images/test-book/image3.jpg")
        ]
        
        return book
    
    @pytest.mark.asyncio
    async def test_mapping_with_media_api_urls(self, sample_book):
        """Test mapping with Media API EPS URLs."""
        # Mock EPS URLs from Media API
        media_api_urls = [
            "https://i.ebayimg.com/images/g/ABC123/image1.jpg",
            "https://i.ebayimg.com/images/g/ABC123/image2.jpg",
            "https://i.ebayimg.com/images/g/ABC123/image3.jpg"
        ]
        
        # Build inventory item with Media API URLs
        inventory_item, title_length, title_truncated = build_inventory_item(
            book=sample_book,
            image_urls=media_api_urls
        )
        
        # Verify inventory item uses Media API URLs
        assert inventory_item["product"]["imageUrls"] == media_api_urls
        assert len(inventory_item["product"]["imageUrls"]) == 3
        assert all(url.startswith("https://") for url in inventory_item["product"]["imageUrls"])
    
    @pytest.mark.asyncio
    async def test_mapping_with_self_host_urls(self, sample_book):
        """Test mapping with self-host URLs."""
        base_url = "http://127.0.0.1:8000"
        
        # Build inventory item with self-host URLs (default behavior)
        inventory_item, title_length, title_truncated = build_inventory_item(
            book=sample_book,
            image_urls=None,  # Will use base_url fallback
            base_url=base_url
        )
        
        # Verify self-host URLs are constructed
        image_urls = inventory_item["product"]["imageUrls"]
        assert len(image_urls) == 3
        assert all(url.startswith(base_url) for url in image_urls)
    
    @pytest.mark.asyncio
    @patch('integrations.ebay.images.resolve_listing_urls')
    async def test_resolve_listing_urls_media_api(self, mock_resolve_urls, sample_book):
        """Test resolve_listing_urls with Media API strategy."""
        # Mock Media API URL resolution
        eps_urls = [
            "https://i.ebayimg.com/images/g/ABC123/image1.jpg",
            "https://i.ebayimg.com/images/g/ABC123/image2.jpg"
        ]
        mock_resolve_urls.return_value = eps_urls
        
        # This would be called in prepare_for_publish
        token = "test-access-token"
        session = MagicMock()
        base_url = "https://api.sandbox.ebay.com"
        
        result_urls = await resolve_listing_urls(
            book_id=sample_book.id,
            token=token,
            session=session,
            base_url=base_url
        )
        
        # Verify URLs are EPS URLs from Media API
        assert result_urls == eps_urls
        assert all(url.startswith("https://i.ebayimg.com") for url in result_urls)
    
    def test_build_mapping_result_with_media_urls(self, sample_book):
        """Test build_mapping_result with Media API URLs."""
        media_api_urls = [
            "https://i.ebayimg.com/images/g/ABC123/image1.jpg",
            "https://i.ebayimg.com/images/g/ABC123/image2.jpg"
        ]
        
        payment_policy_id = "payment-policy-123"
        return_policy_id = "return-policy-123"
        fulfillment_policy_id = "fulfillment-policy-123"
        
        result = build_mapping_result(
            book=sample_book,
            image_urls=media_api_urls,
            payment_policy_id=payment_policy_id,
            return_policy_id=return_policy_id,
            fulfillment_policy_id=fulfillment_policy_id
        )
        
        assert isinstance(result, MappingResult)
        assert result.inventory_item["product"]["imageUrls"] == media_api_urls
        assert result.offer["sku"] == sample_book.id
        assert result.offer["paymentPolicyId"] == payment_policy_id
        assert result.offer["returnPolicyId"] == return_policy_id
        assert result.offer["fulfillmentPolicyId"] == fulfillment_policy_id
    
    def test_image_url_validation(self, sample_book):
        """Test that image URLs are validated (must be HTTPS)."""
        # HTTPS URLs should work
        https_urls = [
            "https://i.ebayimg.com/images/g/ABC123/image1.jpg",
            "https://example.com/image2.jpg"
        ]
        
        inventory_item, _, _ = build_inventory_item(
            book=sample_book,
            image_urls=https_urls
        )
        
        assert inventory_item["product"]["imageUrls"] == https_urls
        
        # HTTP URLs should be rejected (validation happens in publish.py)
        # But mapping layer itself doesn't enforce this
        http_urls = [
            "http://example.com/image1.jpg",  # Not HTTPS
            "https://i.ebayimg.com/images/g/ABC123/image2.jpg"
        ]
        
        # Mapping layer accepts them, but publish.py validates
        inventory_item2, _, _ = build_inventory_item(
            book=sample_book,
            image_urls=http_urls
        )
        
        assert len(inventory_item2["product"]["imageUrls"]) == 2
    
    def test_image_count_limits(self, sample_book):
        """Test image count limits (max 12)."""
        # Create 15 image URLs
        many_urls = [f"https://i.ebayimg.com/images/g/ABC123/image{i}.jpg" for i in range(15)]
        
        inventory_item, _, _ = build_inventory_item(
            book=sample_book,
            image_urls=many_urls
        )
        
        # Should be limited to 12
        assert len(inventory_item["product"]["imageUrls"]) == 12
    
    def test_empty_image_urls_error(self, sample_book):
        """Test that empty image URLs raise error."""
        with pytest.raises(ValueError, match="at least one image"):
            build_inventory_item(
                book=sample_book,
                image_urls=[]
            )
    
    def test_mapping_sku_consistency(self, sample_book):
        """Test that SKU is consistent between inventory item and offer."""
        image_urls = ["https://i.ebayimg.com/images/g/ABC123/image1.jpg"]
        
        inventory_item, _, _ = build_inventory_item(
            book=sample_book,
            image_urls=image_urls
        )
        
        offer = build_offer(
            book=sample_book,
            payment_policy_id="payment-123",
            return_policy_id="return-123",
            fulfillment_policy_id="fulfillment-123"
        )
        
        # SKU should match
        assert inventory_item["sku"] == offer["sku"]
        assert inventory_item["sku"] == sample_book.id


class TestMappingRegression:
    """Regression tests for mapping functionality."""
    
    def test_title_truncation_regression(self):
        """Test that title truncation still works correctly."""
        book = Book(
            id="test-book",
            title_ai="A" * 100,  # 100 character title
            description_ai="Test description",
            condition_grade=ConditionGrade.GOOD,
            price_suggested=19.99,
            quantity=1
        )
        
        book.images = [MockImage("data/images/test-book/image1.jpg")]
        
        inventory_item, title_length, title_truncated = build_inventory_item(
            book=book,
            image_urls=["https://i.ebayimg.com/images/g/ABC123/image1.jpg"]
        )
        
        # Title should be truncated to 80 characters
        assert len(inventory_item["product"]["title"]) <= 80
        assert title_truncated is True
    
    def test_condition_mapping_regression(self):
        """Test that condition mapping still works for all grades."""
        conditions = [
            (ConditionGrade.BRAND_NEW, "1000"),
            (ConditionGrade.LIKE_NEW, "2750"),
            (ConditionGrade.VERY_GOOD, "4000"),
            (ConditionGrade.GOOD, "5000"),
            (ConditionGrade.ACCEPTABLE, "6000")
        ]
        
        for condition_grade, expected_id in conditions:
            book = Book(
                id=f"test-book-{condition_grade.value}",
                title="Test Book",
                description_ai="Test description",
                condition_grade=condition_grade,
                price_suggested=19.99,
                quantity=1
            )
            
            book.images = [MockImage("data/images/test-book/image1.jpg")]
            
            inventory_item, _, _ = build_inventory_item(
                book=book,
                image_urls=["https://i.ebayimg.com/images/g/ABC123/image1.jpg"]
            )
            
            assert inventory_item["product"]["condition"] == expected_id
    
    def test_aspects_building_regression(self):
        """Test that aspects (item specifics) are built correctly."""
        book = Book(
            id="test-book",
            title="Test Book",
            author="Test Author",
            publisher="Test Publisher",
            year="2020",
            isbn13="9781234567890",
            format="Hardcover",
            language="English",
            edition="1st Edition",
            description_ai="Test description",
            condition_grade=ConditionGrade.GOOD,
            price_suggested=19.99,
            quantity=1,
            specifics_ai={
                "topic": "Fiction",
                "genre": "Mystery",
                "signed": True,
                "inscribed": False,
                "features": ["Dust Jacket", "First Edition"]
            }
        )
        
        book.images = [MockImage("data/images/test-book/image1.jpg")]
        
        inventory_item, _, _ = build_inventory_item(
            book=book,
            image_urls=["https://i.ebayimg.com/images/g/ABC123/image1.jpg"]
        )
        
        aspects = inventory_item["product"]["aspects"]
        
        # Verify all aspects are present
        assert aspects["ISBN"] == "9781234567890"
        assert aspects["Author"] == "Test Author"
        assert aspects["Publisher"] == "Test Publisher"
        assert aspects["Publication Year"] == "2020"
        assert aspects["Format"] == "Hardcover"
        assert aspects["Language"] == "English"
        assert aspects["Edition"] == "1st Edition"
        assert aspects["Topic"] == "Fiction"
        assert aspects["Genre"] == "Mystery"
        assert aspects["Signed"] == "Yes"
        assert aspects["Inscribed"] == "No"
        assert "Features" in aspects
        assert isinstance(aspects["Features"], list)
        assert "Dust Jacket" in aspects["Features"]
        assert "First Edition" in aspects["Features"]

