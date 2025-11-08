"""
End-to-End Publish Flow Tests

Tests for /ebay/publish/{book_id} full flow with mocked eBay API.
"""

import pytest
import os
from unittest.mock import patch, MagicMock, AsyncMock
from datetime import datetime
from fastapi.testclient import TestClient

from main import app
from models import Book, Image, BookStatus, ConditionGrade
from db import create_db_and_tables, get_session
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool
from integrations.ebay.token_store import TokenStore, get_encryption


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
def sample_book_with_images(db_session):
    """Create a sample book with images ready for publishing."""
    book = Book(
        id="test-book-publish",
        status=BookStatus.APPROVED,
        title="Test Book for Publishing",
        title_ai="Test Book for Publishing - AI Generated",
        description_ai="This is a test book description",
        author="Test Author",
        publisher="Test Publisher",
        year="2020",
        isbn13="9781234567890",
        condition_grade=ConditionGrade.GOOD,
        price_suggested=19.99,
        quantity=1,
        verified=True
    )
    db_session.add(book)
    
    # Add images
    image1 = Image(
        id="img-1",
        book_id=book.id,
        path="data/images/test-book-publish/image1.jpg",
        width=1600,
        height=1200,
        hash="hash1"
    )
    image2 = Image(
        id="img-2",
        book_id=book.id,
        path="data/images/test-book-publish/image2.jpg",
        width=1600,
        height=1200,
        hash="hash2"
    )
    db_session.add(image1)
    db_session.add(image2)
    
    db_session.commit()
    db_session.refresh(book)
    
    return book


@pytest.fixture
def oauth_token(db_session):
    """Create a valid OAuth token."""
    encryption = get_encryption()
    token_store = TokenStore(db_session, encryption)
    
    now = int(datetime.now().timestamp() * 1000)
    expires_at = now + (7200 * 1000)  # 2 hours
    
    token = token_store.save_token(
        provider="ebay",
        access_token="test-access-token",
        refresh_token="test-refresh-token",
        expires_in=7200,
        token_type="Bearer",
        scope="sell.inventory sell.account"
    )
    
    return token


class TestPublishEndpoints:
    """Test publish endpoints."""
    
    def test_publish_book_not_found(self, client):
        """Test publishing non-existent book."""
        response = client.post("/ebay/publish/nonexistent-book")
        assert response.status_code == 404
    
    def test_publish_status_not_found(self, client):
        """Test getting publish status for non-existent book."""
        response = client.get("/ebay/publish/nonexistent-book/status")
        assert response.status_code == 404
    
    @patch('integrations.ebay.client.EBayClient.create_or_replace_inventory_item')
    @patch('integrations.ebay.client.EBayClient.create_offer')
    @patch('integrations.ebay.client.EBayClient.publish_offer')
    @patch('integrations.ebay.images.resolve_listing_urls')
    def test_publish_book_full_flow(
        self,
        mock_resolve_urls,
        mock_publish_offer,
        mock_create_offer,
        mock_create_inv,
        client,
        db_session,
        sample_book_with_images,
        oauth_token,
        tmp_path,
        monkeypatch
    ):
        """Test full publish flow with mocked eBay API."""
        # Mock image URL resolution (self-host strategy)
        mock_resolve_urls.return_value = [
            "https://example.com/images/image1.jpg",
            "https://example.com/images/image2.jpg"
        ]
        
        # Mock inventory item creation
        mock_create_inv.return_value = (True, {}, None)
        
        # Mock offer creation
        mock_create_offer.return_value = (True, {"offerId": "test-offer-123"}, "test-offer-123", None)
        
        # Mock publish offer
        mock_publish_offer.return_value = (True, {"listingId": "test-listing-456"}, "test-listing-456", None)
        
        # Set environment to sandbox for testing
        monkeypatch.setenv("EBAY_ENV", "sandbox")
        monkeypatch.setenv("EBAY_PAYMENT_POLICY_ID", "test-payment-policy")
        monkeypatch.setenv("EBAY_RETURN_POLICY_ID", "test-return-policy")
        monkeypatch.setenv("EBAY_FULFILLMENT_POLICY_ID", "test-fulfillment-policy")
        
        response = client.post(f"/ebay/publish/{sample_book_with_images.id}")
        
        # Should succeed
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["book_id"] == sample_book_with_images.id
        assert data["offer_id"] == "test-offer-123"
        assert data["listing_id"] == "test-listing-456"
        assert data["listing_url"] is not None
        
        # Verify book was updated
        db_session.refresh(sample_book_with_images)
        assert sample_book_with_images.sku == sample_book_with_images.id
        assert sample_book_with_images.ebay_offer_id == "test-offer-123"
        assert sample_book_with_images.ebay_listing_id == "test-listing-456"
        assert sample_book_with_images.publish_status == "published"
    
    @patch('integrations.ebay.client.EBayClient.create_or_replace_inventory_item')
    @patch('integrations.ebay.images.resolve_listing_urls')
    def test_publish_book_inventory_failure(
        self,
        mock_resolve_urls,
        mock_create_inv,
        client,
        db_session,
        sample_book_with_images,
        oauth_token,
        monkeypatch
    ):
        """Test publish flow when inventory item creation fails."""
        mock_resolve_urls.return_value = ["https://example.com/images/image1.jpg"]
        mock_create_inv.return_value = (False, {}, "Inventory creation failed")
        
        monkeypatch.setenv("EBAY_ENV", "sandbox")
        monkeypatch.setenv("EBAY_PAYMENT_POLICY_ID", "test-payment-policy")
        monkeypatch.setenv("EBAY_RETURN_POLICY_ID", "test-return-policy")
        monkeypatch.setenv("EBAY_FULFILLMENT_POLICY_ID", "test-fulfillment-policy")
        
        response = client.post(f"/ebay/publish/{sample_book_with_images.id}")
        
        assert response.status_code == 400
        data = response.json()
        assert data["success"] is False
        assert "error" in data
        assert "Inventory item creation failed" in data["error"]
    
    @patch('integrations.ebay.client.EBayClient.create_or_replace_inventory_item')
    @patch('integrations.ebay.client.EBayClient.create_offer')
    @patch('integrations.ebay.images.resolve_listing_urls')
    def test_publish_book_offer_failure(
        self,
        mock_resolve_urls,
        mock_create_offer,
        mock_create_inv,
        client,
        db_session,
        sample_book_with_images,
        oauth_token,
        monkeypatch
    ):
        """Test publish flow when offer creation fails."""
        mock_resolve_urls.return_value = ["https://example.com/images/image1.jpg"]
        mock_create_inv.return_value = (True, {}, None)
        mock_create_offer.return_value = (False, {}, None, "Offer creation failed")
        
        monkeypatch.setenv("EBAY_ENV", "sandbox")
        monkeypatch.setenv("EBAY_PAYMENT_POLICY_ID", "test-payment-policy")
        monkeypatch.setenv("EBAY_RETURN_POLICY_ID", "test-return-policy")
        monkeypatch.setenv("EBAY_FULFILLMENT_POLICY_ID", "test-fulfillment-policy")
        
        response = client.post(f"/ebay/publish/{sample_book_with_images.id}")
        
        assert response.status_code == 400
        data = response.json()
        assert data["success"] is False
        assert "Offer creation failed" in data["error"]
    
    def test_publish_status_endpoint(self, client, db_session, sample_book_with_images):
        """Test GET /ebay/publish/{book_id}/status endpoint."""
        # Set publish status
        sample_book_with_images.sku = sample_book_with_images.id
        sample_book_with_images.ebay_offer_id = "test-offer-123"
        sample_book_with_images.ebay_listing_id = "test-listing-456"
        sample_book_with_images.publish_status = "published"
        db_session.add(sample_book_with_images)
        db_session.commit()
        
        response = client.get(f"/ebay/publish/{sample_book_with_images.id}/status")
        
        assert response.status_code == 200
        data = response.json()
        assert data["book_id"] == sample_book_with_images.id
        assert data["sku"] == sample_book_with_images.id
        assert data["offer_id"] == "test-offer-123"
        assert data["listing_id"] == "test-listing-456"
        assert data["publish_status"] == "published"
        assert data["listing_url"] is not None


class TestPublishValidation:
    """Test publish validation."""
    
    def test_publish_book_no_price(self, client, db_session, sample_book_with_images, oauth_token):
        """Test publishing book without price."""
        sample_book_with_images.price_suggested = None
        db_session.add(sample_book_with_images)
        db_session.commit()
        
        response = client.post(f"/ebay/publish/{sample_book_with_images.id}")
        
        assert response.status_code == 400
    
    def test_publish_book_no_oauth_token(self, client, db_session, sample_book_with_images):
        """Test publishing book without OAuth token."""
        response = client.post(f"/ebay/publish/{sample_book_with_images.id}")
        
        assert response.status_code == 401


class TestEBayClient:
    """Test eBay client functionality."""
    
    @patch('integrations.ebay.client.requests.request')
    def test_create_inventory_item(self, mock_request, db_session, oauth_token):
        """Test creating inventory item via eBay client."""
        from integrations.ebay.client import EBayClient
        
        mock_response = MagicMock()
        mock_response.status_code = 204
        mock_response.content = b""
        mock_response.json.return_value = {}
        mock_request.return_value = mock_response
        
        client = EBayClient(db_session)
        success, response_data, error = client.create_or_replace_inventory_item(
            sku="test-sku",
            inventory_item={"sku": "test-sku", "product": {"title": "Test"}}
        )
        
        assert success is True
        assert error is None
        mock_request.assert_called_once()
    
    @patch('integrations.ebay.client.requests.request')
    def test_create_offer(self, mock_request, db_session, oauth_token):
        """Test creating offer via eBay client."""
        from integrations.ebay.client import EBayClient
        
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {"offerId": "test-offer-123"}
        mock_request.return_value = mock_response
        
        client = EBayClient(db_session)
        success, response_data, offer_id, error = client.create_offer(
            offer={"sku": "test-sku", "marketplaceId": "EBAY_US"}
        )
        
        assert success is True
        assert offer_id == "test-offer-123"
        assert error is None
    
    @patch('integrations.ebay.client.requests.request')
    def test_publish_offer(self, mock_request, db_session, oauth_token):
        """Test publishing offer via eBay client."""
        from integrations.ebay.client import EBayClient
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"listingId": "test-listing-456"}
        mock_request.return_value = mock_response
        
        client = EBayClient(db_session)
        success, response_data, listing_id, error = client.publish_offer("test-offer-123")
        
        assert success is True
        assert listing_id == "test-listing-456"
        assert error is None

