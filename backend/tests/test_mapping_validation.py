"""
Mapping Validation Tests

Tests for eBay mapping validation functionality.
"""

import pytest
from integrations.ebay.mapping_validation import (
    validate_required_fields,
    validate_title_length,
    EBAY_TITLE_MAX_LENGTH
)


class TestMappingValidation:
    """Test mapping validation functionality."""
    
    @pytest.fixture
    def valid_inventory_item(self):
        """Create a valid inventory item payload."""
        return {
            "sku": "test-book-123",
            "product": {
                "title": "Valid Title",
                "description": "Valid description",
                "imageUrls": ["http://example.com/image1.jpg"],
                "condition": "5000",
                "aspects": {
                    "ISBN": "9781234567890",
                    "Author": "Test Author"
                }
            }
        }
    
    @pytest.fixture
    def valid_offer(self):
        """Create a valid offer payload."""
        return {
            "sku": "test-book-123",
            "marketplaceId": "EBAY_US",
            "format": "FIXED_PRICE",
            "categoryId": "267",
            "pricing": {
                "price": {
                    "value": "19.99",
                    "currency": "USD"
                }
            },
            "quantity": 1,
            "fulfillmentPolicyId": "FULFILLMENT_123",
            "paymentPolicyId": "PAYMENT_456",
            "returnPolicyId": "RETURN_789"
        }
    
    def test_validate_required_fields_valid(self, valid_inventory_item, valid_offer):
        """Test validation with valid payloads."""
        errors = validate_required_fields(valid_inventory_item, valid_offer)
        assert len(errors) == 0
    
    def test_validate_inventory_item_missing_sku(self, valid_offer):
        """Test validation error when SKU is missing."""
        inv = {
            "product": {
                "title": "Title",
                "description": "Description",
                "imageUrls": ["http://example.com/img.jpg"],
                "condition": "5000"
            }
        }
        
        errors = validate_required_fields(inv, valid_offer)
        assert any("sku" in error.lower() and "inventory item" in error.lower() for error in errors)
    
    def test_validate_inventory_item_missing_product(self, valid_offer):
        """Test validation error when product is missing."""
        inv = {"sku": "test-123"}
        
        errors = validate_required_fields(inv, valid_offer)
        assert any("product" in error.lower() for error in errors)
    
    def test_validate_inventory_item_missing_title(self, valid_offer):
        """Test validation error when title is missing."""
        inv = {
            "sku": "test-123",
            "product": {
                "description": "Description",
                "imageUrls": ["http://example.com/img.jpg"],
                "condition": "5000"
            }
        }
        
        errors = validate_required_fields(inv, valid_offer)
        assert any("title" in error.lower() for error in errors)
    
    def test_validate_inventory_item_title_too_long(self, valid_offer):
        """Test validation error when title exceeds max length."""
        long_title = "A" * (EBAY_TITLE_MAX_LENGTH + 1)
        inv = {
            "sku": "test-123",
            "product": {
                "title": long_title,
                "description": "Description",
                "imageUrls": ["http://example.com/img.jpg"],
                "condition": "5000"
            }
        }
        
        errors = validate_required_fields(inv, valid_offer)
        assert any("title" in error.lower() and "exceeds" in error.lower() for error in errors)
    
    def test_validate_inventory_item_missing_description(self, valid_offer):
        """Test validation error when description is missing."""
        inv = {
            "sku": "test-123",
            "product": {
                "title": "Title",
                "imageUrls": ["http://example.com/img.jpg"],
                "condition": "5000"
            }
        }
        
        errors = validate_required_fields(inv, valid_offer)
        assert any("description" in error.lower() for error in errors)
    
    def test_validate_inventory_item_missing_images(self, valid_offer):
        """Test validation error when images are missing."""
        inv = {
            "sku": "test-123",
            "product": {
                "title": "Title",
                "description": "Description",
                "imageUrls": [],
                "condition": "5000"
            }
        }
        
        errors = validate_required_fields(inv, valid_offer)
        assert any("image" in error.lower() for error in errors)
    
    def test_validate_inventory_item_too_many_images(self, valid_offer):
        """Test validation error when too many images."""
        inv = {
            "sku": "test-123",
            "product": {
                "title": "Title",
                "description": "Description",
                "imageUrls": [f"http://example.com/img{i}.jpg" for i in range(13)],
                "condition": "5000"
            }
        }
        
        errors = validate_required_fields(inv, valid_offer)
        assert any("image" in error.lower() and "too many" in error.lower() for error in errors)
    
    def test_validate_inventory_item_missing_condition(self, valid_offer):
        """Test validation error when condition is missing."""
        inv = {
            "sku": "test-123",
            "product": {
                "title": "Title",
                "description": "Description",
                "imageUrls": ["http://example.com/img.jpg"]
            }
        }
        
        errors = validate_required_fields(inv, valid_offer)
        assert any("condition" in error.lower() for error in errors)
    
    def test_validate_offer_missing_sku(self, valid_inventory_item):
        """Test validation error when offer SKU is missing."""
        offer = {
            "marketplaceId": "EBAY_US",
            "format": "FIXED_PRICE",
            "categoryId": "267",
            "pricing": {"price": {"value": "19.99", "currency": "USD"}},
            "quantity": 1,
            "fulfillmentPolicyId": "FUL",
            "paymentPolicyId": "PAY",
            "returnPolicyId": "RET"
        }
        
        errors = validate_required_fields(valid_inventory_item, offer)
        assert any("sku" in error.lower() and "offer" in error.lower() for error in errors)
    
    def test_validate_offer_wrong_marketplace(self, valid_inventory_item):
        """Test validation error when marketplace ID is wrong."""
        offer = {
            "sku": "test-123",
            "marketplaceId": "EBAY_UK",  # Wrong
            "format": "FIXED_PRICE",
            "categoryId": "267",
            "pricing": {"price": {"value": "19.99", "currency": "USD"}},
            "quantity": 1,
            "fulfillmentPolicyId": "FUL",
            "paymentPolicyId": "PAY",
            "returnPolicyId": "RET"
        }
        
        errors = validate_required_fields(valid_inventory_item, offer)
        assert any("marketplaceId" in error.lower() for error in errors)
    
    def test_validate_offer_wrong_format(self, valid_inventory_item):
        """Test validation error when format is wrong."""
        offer = {
            "sku": "test-123",
            "marketplaceId": "EBAY_US",
            "format": "AUCTION",  # Wrong
            "categoryId": "267",
            "pricing": {"price": {"value": "19.99", "currency": "USD"}},
            "quantity": 1,
            "fulfillmentPolicyId": "FUL",
            "paymentPolicyId": "PAY",
            "returnPolicyId": "RET"
        }
        
        errors = validate_required_fields(valid_inventory_item, offer)
        assert any("format" in error.lower() for error in errors)
    
    def test_validate_offer_wrong_category(self, valid_inventory_item):
        """Test validation error when category ID is wrong."""
        offer = {
            "sku": "test-123",
            "marketplaceId": "EBAY_US",
            "format": "FIXED_PRICE",
            "categoryId": "999",  # Wrong
            "pricing": {"price": {"value": "19.99", "currency": "USD"}},
            "quantity": 1,
            "fulfillmentPolicyId": "FUL",
            "paymentPolicyId": "PAY",
            "returnPolicyId": "RET"
        }
        
        errors = validate_required_fields(valid_inventory_item, offer)
        assert any("categoryId" in error.lower() for error in errors)
    
    def test_validate_offer_missing_pricing(self, valid_inventory_item):
        """Test validation error when pricing is missing."""
        offer = {
            "sku": "test-123",
            "marketplaceId": "EBAY_US",
            "format": "FIXED_PRICE",
            "categoryId": "267",
            "quantity": 1,
            "fulfillmentPolicyId": "FUL",
            "paymentPolicyId": "PAY",
            "returnPolicyId": "RET"
        }
        
        errors = validate_required_fields(valid_inventory_item, offer)
        assert any("pricing" in error.lower() for error in errors)
    
    def test_validate_offer_missing_price_value(self, valid_inventory_item):
        """Test validation error when price value is missing."""
        offer = {
            "sku": "test-123",
            "marketplaceId": "EBAY_US",
            "format": "FIXED_PRICE",
            "categoryId": "267",
            "pricing": {"price": {"currency": "USD"}},  # Missing value
            "quantity": 1,
            "fulfillmentPolicyId": "FUL",
            "paymentPolicyId": "PAY",
            "returnPolicyId": "RET"
        }
        
        errors = validate_required_fields(valid_inventory_item, offer)
        assert any("price.value" in error.lower() for error in errors)
    
    def test_validate_offer_wrong_currency(self, valid_inventory_item):
        """Test validation error when currency is wrong."""
        offer = {
            "sku": "test-123",
            "marketplaceId": "EBAY_US",
            "format": "FIXED_PRICE",
            "categoryId": "267",
            "pricing": {"price": {"value": "19.99", "currency": "EUR"}},  # Wrong
            "quantity": 1,
            "fulfillmentPolicyId": "FUL",
            "paymentPolicyId": "PAY",
            "returnPolicyId": "RET"
        }
        
        errors = validate_required_fields(valid_inventory_item, offer)
        assert any("currency" in error.lower() for error in errors)
    
    def test_validate_offer_missing_quantity(self, valid_inventory_item):
        """Test validation error when quantity is missing."""
        offer = {
            "sku": "test-123",
            "marketplaceId": "EBAY_US",
            "format": "FIXED_PRICE",
            "categoryId": "267",
            "pricing": {"price": {"value": "19.99", "currency": "USD"}},
            "fulfillmentPolicyId": "FUL",
            "paymentPolicyId": "PAY",
            "returnPolicyId": "RET"
        }
        
        errors = validate_required_fields(valid_inventory_item, offer)
        assert any("quantity" in error.lower() for error in errors)
    
    def test_validate_offer_invalid_quantity(self, valid_inventory_item):
        """Test validation error when quantity is invalid."""
        offer = {
            "sku": "test-123",
            "marketplaceId": "EBAY_US",
            "format": "FIXED_PRICE",
            "categoryId": "267",
            "pricing": {"price": {"value": "19.99", "currency": "USD"}},
            "quantity": 0,  # Invalid
            "fulfillmentPolicyId": "FUL",
            "paymentPolicyId": "PAY",
            "returnPolicyId": "RET"
        }
        
        errors = validate_required_fields(valid_inventory_item, offer)
        assert any("quantity" in error.lower() and ">=" in error.lower() for error in errors)
    
    def test_validate_offer_missing_policy_ids(self, valid_inventory_item):
        """Test validation errors when policy IDs are missing."""
        # Missing fulfillment policy
        offer1 = {
            "sku": "test-123",
            "marketplaceId": "EBAY_US",
            "format": "FIXED_PRICE",
            "categoryId": "267",
            "pricing": {"price": {"value": "19.99", "currency": "USD"}},
            "quantity": 1,
            "paymentPolicyId": "PAY",
            "returnPolicyId": "RET"
        }
        errors1 = validate_required_fields(valid_inventory_item, offer1)
        assert any("fulfillmentPolicyId" in error for error in errors1)
        
        # Missing payment policy
        offer2 = {**offer1, "fulfillmentPolicyId": "FUL"}
        del offer2["paymentPolicyId"]
        errors2 = validate_required_fields(valid_inventory_item, offer2)
        assert any("paymentPolicyId" in error for error in errors2)
        
        # Missing return policy
        offer3 = {**offer1, "fulfillmentPolicyId": "FUL", "paymentPolicyId": "PAY"}
        del offer3["returnPolicyId"]
        errors3 = validate_required_fields(valid_inventory_item, offer3)
        assert any("returnPolicyId" in error for error in errors3)
    
    def test_validate_sku_mismatch(self, valid_inventory_item, valid_offer):
        """Test validation error when SKUs don't match."""
        valid_offer["sku"] = "different-sku"
        
        errors = validate_required_fields(valid_inventory_item, valid_offer)
        assert any("sku" in error.lower() and "match" in error.lower() for error in errors)
    
    def test_validate_title_length_valid(self):
        """Test title length validation with valid title."""
        title = "Valid Title"
        length, truncated = validate_title_length(title)
        
        assert length == len(title)
        assert truncated == False
    
    def test_validate_title_length_exceeds(self):
        """Test title length validation with title exceeding limit."""
        long_title = "A" * (EBAY_TITLE_MAX_LENGTH + 10)
        length, truncated = validate_title_length(long_title)
        
        assert length == len(long_title)
        assert truncated == True
    
    def test_validate_title_length_exact_limit(self):
        """Test title length validation with title exactly at limit."""
        exact_title = "A" * EBAY_TITLE_MAX_LENGTH
        length, truncated = validate_title_length(exact_title)
        
        assert length == EBAY_TITLE_MAX_LENGTH
        assert truncated == False

