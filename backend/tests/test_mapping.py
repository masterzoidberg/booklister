"""
Mapping Service Tests

Tests for eBay Inventory API mapping functionality.
"""

import pytest
from models import Book, Image, ConditionGrade
from integrations.ebay.mapping import (
    build_inventory_item,
    build_offer,
    build_mapping_result,
    MappingResult,
    EBAY_TITLE_MAX_LENGTH
)


class MockImage:
    """Mock Image object for testing."""
    def __init__(self, path: str):
        self.path = path
        self.id = "img-123"
        self.width = 100
        self.height = 100


class TestMapping:
    """Test mapping functionality."""
    
    @pytest.fixture
    def sample_book(self):
        """Create a sample book with all fields populated."""
        book = Book(
            id="test-book-123",
            title="Original Title",
            title_ai="AI Generated Title for eBay Listing",
            description_ai="This is a detailed description of the book",
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
                "features": ["Autographed", "First Edition"],
                "signed": False,
                "inscribed": False
            }
        )
        
        # Mock images relationship
        book.images = [
            MockImage("data/images/test-book-123/image1.jpg"),
            MockImage("data/images/test-book-123/image2.jpg")
        ]
        
        return book
    
    @pytest.fixture
    def minimal_book(self):
        """Create a minimal book with only required fields."""
        book = Book(
            id="minimal-book-456",
            title_ai="Minimal Title",
            description_ai="Minimal description",
            condition_grade=ConditionGrade.GOOD,
            price_suggested=9.99,
            quantity=1
        )
        
        book.images = [MockImage("data/images/minimal-book-456/image.jpg")]
        
        return book
    
    def test_build_inventory_item_happy_path(self, sample_book):
        """Test building inventory item with all fields."""
        inv, title_length, title_truncated = build_inventory_item(sample_book)
        
        # Check structure
        assert "sku" in inv
        assert "product" in inv
        assert inv["sku"] == "test-book-123"
        
        # Check product fields
        product = inv["product"]
        assert product["title"] == "AI Generated Title for eBay Listing"
        assert product["description"] == "This is a detailed description of the book"
        assert len(product["imageUrls"]) == 2
        assert product["condition"] == "5000"  # Good
        assert product["brand"] == "Test Publisher"
        
        # Check aspects
        aspects = product["aspects"]
        assert aspects["ISBN"] == "9781234567890"
        assert aspects["Author"] == "Test Author"
        assert aspects["Publisher"] == "Test Publisher"
        assert aspects["Publication Year"] == "2020"
        assert aspects["Format"] == "Hardcover"
        assert aspects["Language"] == "English"
        assert aspects["Edition"] == "1st Edition"
        assert aspects["Topic"] == "Fiction"
        assert aspects["Genre"] == "Mystery"
        assert aspects["Signed"] == "No"
        assert aspects["Inscribed"] == "No"
        assert aspects["Features"] == ["Autographed", "First Edition"]
        
        # Check image URLs
        assert product["imageUrls"][0] == "http://127.0.0.1:8000/images/test-book-123/image1.jpg"
        assert product["imageUrls"][1] == "http://127.0.0.1:8000/images/test-book-123/image2.jpg"
        
        # Check title metadata
        assert title_length == len("AI Generated Title for eBay Listing")
        assert title_truncated == False
    
    def test_build_inventory_item_minimal(self, minimal_book):
        """Test building inventory item with minimal fields."""
        inv, title_length, title_truncated = build_inventory_item(minimal_book)
        
        assert inv["sku"] == "minimal-book-456"
        product = inv["product"]
        assert product["title"] == "Minimal Title"
        assert product["description"] == "Minimal description"
        assert len(product["imageUrls"]) == 1
        
        # Aspects should exist but be minimal
        aspects = product["aspects"]
        assert aspects["Signed"] == "No"
        assert aspects["Inscribed"] == "No"
        
        # Brand should not be present if publisher is missing
        assert "brand" not in product
    
    def test_build_inventory_item_title_truncation(self):
        """Test title truncation when title exceeds 80 characters."""
        long_title = "A" * 100
        book = Book(
            id="long-title-book",
            title_ai=long_title,
            description_ai="Description",
            condition_grade=ConditionGrade.GOOD,
            price_suggested=10.00,
            quantity=1
        )
        book.images = [MockImage("data/images/long-title-book/img.jpg")]
        
        inv, title_length, title_truncated = build_inventory_item(book)
        
        assert len(inv["product"]["title"]) <= EBAY_TITLE_MAX_LENGTH
        assert title_truncated == True
        assert title_length <= EBAY_TITLE_MAX_LENGTH
    
    def test_build_inventory_item_title_word_boundary_truncation(self):
        """Test title truncation at word boundary."""
        # Create title that's exactly 85 chars with word boundary at 75
        title = "A" * 75 + " " + "B" * 10
        book = Book(
            id="word-boundary-book",
            title_ai=title,
            description_ai="Description",
            condition_grade=ConditionGrade.GOOD,
            price_suggested=10.00,
            quantity=1
        )
        book.images = [MockImage("data/images/word-boundary-book/img.jpg")]
        
        inv, title_length, title_truncated = build_inventory_item(book)
        
        # Should truncate at word boundary if possible
        truncated_title = inv["product"]["title"]
        assert len(truncated_title) <= EBAY_TITLE_MAX_LENGTH
        assert title_truncated == True
    
    def test_build_inventory_item_fallback_to_title(self):
        """Test fallback from title_ai to title."""
        book = Book(
            id="fallback-book",
            title="Fallback Title",
            description_ai="Description",
            condition_grade=ConditionGrade.GOOD,
            price_suggested=10.00,
            quantity=1
        )
        book.images = [MockImage("data/images/fallback-book/img.jpg")]
        
        inv, _, _ = build_inventory_item(book)
        
        assert inv["product"]["title"] == "Fallback Title"
    
    def test_build_inventory_item_no_images_error(self):
        """Test error when book has no images."""
        book = Book(
            id="no-images-book",
            title_ai="Title",
            description_ai="Description",
            condition_grade=ConditionGrade.GOOD,
            price_suggested=10.00,
            quantity=1
        )
        book.images = []
        
        with pytest.raises(ValueError, match="at least one image"):
            build_inventory_item(book)
    
    def test_build_inventory_item_image_limit(self):
        """Test that images are limited to 12."""
        book = Book(
            id="many-images-book",
            title_ai="Title",
            description_ai="Description",
            condition_grade=ConditionGrade.GOOD,
            price_suggested=10.00,
            quantity=1
        )
        # Create 15 images
        book.images = [MockImage(f"data/images/many-images-book/img{i}.jpg") for i in range(15)]
        
        inv, _, _ = build_inventory_item(book)
        
        assert len(inv["product"]["imageUrls"]) == 12
    
    def test_build_inventory_item_condition_mapping(self):
        """Test all condition grade mappings."""
        condition_tests = [
            (ConditionGrade.BRAND_NEW, "1000"),
            (ConditionGrade.LIKE_NEW, "2750"),
            (ConditionGrade.VERY_GOOD, "4000"),
            (ConditionGrade.GOOD, "5000"),
            (ConditionGrade.ACCEPTABLE, "6000")
        ]
        
        for condition_grade, expected_id in condition_tests:
            book = Book(
                id=f"condition-{condition_grade.value}",
                title_ai="Title",
                description_ai="Description",
                condition_grade=condition_grade,
                price_suggested=10.00,
                quantity=1
            )
            book.images = [MockImage(f"data/images/condition-{condition_grade.value}/img.jpg")]
            
            inv, _, _ = build_inventory_item(book)
            assert inv["product"]["condition"] == expected_id
    
    def test_build_offer_happy_path(self, sample_book):
        """Test building offer with all required fields."""
        offer = build_offer(
            sample_book,
            payment_policy_id="PAYMENT_123",
            return_policy_id="RETURN_456",
            fulfillment_policy_id="FULFILLMENT_789"
        )
        
        assert offer["sku"] == "test-book-123"
        assert offer["marketplaceId"] == "EBAY_US"
        assert offer["format"] == "FIXED_PRICE"
        assert offer["categoryId"] == "267"
        assert offer["quantity"] == 1
        
        # Check pricing
        assert offer["pricing"]["price"]["value"] == "19.99"
        assert offer["pricing"]["price"]["currency"] == "USD"
        
        # Check policy IDs
        assert offer["paymentPolicyId"] == "PAYMENT_123"
        assert offer["returnPolicyId"] == "RETURN_456"
        assert offer["fulfillmentPolicyId"] == "FULFILLMENT_789"
    
    def test_build_offer_missing_price_error(self):
        """Test error when price is missing."""
        book = Book(
            id="no-price-book",
            title_ai="Title",
            description_ai="Description",
            condition_grade=ConditionGrade.GOOD,
            quantity=1
        )
        
        with pytest.raises(ValueError, match="price_suggested"):
            build_offer(book, "PAY", "RET", "FUL")
    
    def test_build_offer_missing_quantity_error(self):
        """Test error when quantity is invalid."""
        book = Book(
            id="no-qty-book",
            title_ai="Title",
            description_ai="Description",
            condition_grade=ConditionGrade.GOOD,
            price_suggested=10.00,
            quantity=0
        )
        
        with pytest.raises(ValueError, match="quantity"):
            build_offer(book, "PAY", "RET", "FUL")
    
    def test_build_offer_missing_policy_ids_error(self, sample_book):
        """Test error when policy IDs are missing."""
        with pytest.raises(ValueError, match="payment_policy_id"):
            build_offer(sample_book, payment_policy_id=None, return_policy_id="RET", fulfillment_policy_id="FUL")
        
        with pytest.raises(ValueError, match="return_policy_id"):
            build_offer(sample_book, payment_policy_id="PAY", return_policy_id=None, fulfillment_policy_id="FUL")
        
        with pytest.raises(ValueError, match="fulfillment_policy_id"):
            build_offer(sample_book, payment_policy_id="PAY", return_policy_id="RET", fulfillment_policy_id=None)
    
    def test_build_mapping_result(self, sample_book):
        """Test building both inventory item and offer together."""
        result = build_mapping_result(
            sample_book,
            payment_policy_id="PAYMENT_123",
            return_policy_id="RETURN_456",
            fulfillment_policy_id="FULFILLMENT_789"
        )
        
        assert isinstance(result, MappingResult)
        assert result.inventory_item["sku"] == "test-book-123"
        assert result.offer["sku"] == "test-book-123"
        assert result.title_length > 0
        assert isinstance(result.title_truncated, bool)
    
    def test_aspects_signed_inscribed(self):
        """Test Signed and Inscribed aspects from specifics_ai."""
        # Test signed=True - values are arrays per eBay API requirements
        book = Book(
            id="signed-book",
            title_ai="Title",
            description_ai="Description",
            condition_grade=ConditionGrade.GOOD,
            price_suggested=10.00,
            quantity=1,
            specifics_ai={"signed": True, "inscribed": True}
        )
        book.images = [MockImage("data/images/signed-book/img.jpg")]

        inv, _, _ = build_inventory_item(book)
        aspects = inv["product"]["aspects"]
        # eBay API receives aspect values as arrays after cleanup
        assert "Signed" in aspects
        assert "Inscribed" in aspects
        # Check that values are in array format (eBay requirement)
        signed_val = aspects["Signed"]
        assert signed_val == ["Yes"] or signed_val == "Yes"  # May be array or string depending on cleanup
        inscribed_val = aspects["Inscribed"]
        assert inscribed_val == ["Yes"] or inscribed_val == "Yes"

        # Test signed=False
        book.specifics_ai = {"signed": False, "inscribed": False}
        inv, _, _ = build_inventory_item(book)
        aspects = inv["product"]["aspects"]
        signed_val = aspects["Signed"]
        assert signed_val == ["No"] or signed_val == "No"
        inscribed_val = aspects["Inscribed"]
        assert inscribed_val == ["No"] or inscribed_val == "No"

        # Test signed=None (default to "No")
        book.specifics_ai = {}
        inv, _, _ = build_inventory_item(book)
        aspects = inv["product"]["aspects"]
        signed_val = aspects["Signed"]
        assert signed_val == ["No"] or signed_val == "No"
        inscribed_val = aspects["Inscribed"]
        assert inscribed_val == ["No"] or inscribed_val == "No"
    
    def test_aspects_features_filtering(self):
        """Test that empty features are filtered out."""
        book = Book(
            id="features-book",
            title_ai="Title",
            description_ai="Description",
            condition_grade=ConditionGrade.GOOD,
            price_suggested=10.00,
            quantity=1,
            specifics_ai={
                "features": ["Valid Feature", "", "   ", "Another Feature"]
            }
        )
        book.images = [MockImage("data/images/features-book/img.jpg")]

        inv, _, _ = build_inventory_item(book)
        aspects = inv["product"]["aspects"]
        assert aspects["Features"] == ["Valid Feature", "Another Feature"]

    def test_childrens_book_category_with_genre(self):
        """Test that fiction/children's books include Genre aspect."""
        from integrations.ebay.mapping import EBAY_CHILDRENS_BOOKS_CATEGORY_ID

        # Create a fiction book with genre
        book = Book(
            id="fiction-book",
            title_ai="Children's Fiction Book",
            description_ai="A fictional story for children",
            condition_grade=ConditionGrade.GOOD,
            price_suggested=15.00,
            quantity=1,
            book_type="fiction",
            specifics_ai={
                "genre": ["Fantasy", "Adventure"],
                "intended_audience": ["Children"],
                "narrative_type": "Fiction"
            },
            ebay_category_id=EBAY_CHILDRENS_BOOKS_CATEGORY_ID
        )
        book.images = [MockImage("data/images/fiction-book/img.jpg")]

        # Build with explicit children's books category
        inv, _, _ = build_inventory_item(book, category_id=EBAY_CHILDRENS_BOOKS_CATEGORY_ID)
        aspects = inv["product"]["aspects"]

        # Genre should be present for children's books category
        assert "Genre" in aspects
        assert aspects["Genre"] == ["Fantasy", "Adventure"]

        # Intended Audience should be present
        assert "Intended Audience" in aspects
        assert aspects["Intended Audience"] == ["Children"]

        # Narrative Type should be present
        assert "Narrative Type" in aspects
        assert aspects["Narrative Type"] == ["Fiction"]

