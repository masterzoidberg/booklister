"""
OAuth Integration Tests

Tests for OAuth token exchange and refresh functionality.
"""

import pytest
import os
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta
from fastapi.testclient import TestClient

from main import app
from models import Token
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


class TestOAuthEndpoints:
    """Test OAuth endpoints."""
    
    def test_auth_url_endpoint(self, client):
        """Test GET /ebay/oauth/auth-url endpoint."""
        with patch('routes.ebay_oauth.get_oauth_config') as mock_config:
            mock_oauth_flow = MagicMock()
            mock_oauth_flow.get_authorization_url.return_value = "https://auth.ebay.com/oauth/authorize?client_id=test&redirect_uri=test&response_type=code&scope=test"
            
            mock_config_instance = MagicMock()
            mock_config.return_value = mock_config_instance
            
            with patch('routes.ebay_oauth.OAuthFlow', return_value=mock_oauth_flow):
                response = client.get("/ebay/oauth/auth-url")
                
                assert response.status_code == 200
                data = response.json()
                assert "auth_url" in data
    
    def test_oauth_status_not_connected(self, client, db_session):
        """Test OAuth status when not connected."""
        response = client.get("/ebay/oauth/status")
        
        assert response.status_code == 200
        data = response.json()
        assert data["connected"] is False
    
    def test_oauth_status_connected(self, client, db_session):
        """Test OAuth status when connected."""
        # Create a token
        encryption = get_encryption()
        token_store = TokenStore(db_session, encryption)
        
        now = int(datetime.now().timestamp() * 1000)
        expires_at = now + (7200 * 1000)  # 2 hours
        
        token = Token(
            provider="ebay",
            access_token=encryption.encrypt("test-access-token"),
            refresh_token=encryption.encrypt("test-refresh-token"),
            expires_at=expires_at,
            token_type="Bearer",
            scope="sell.inventory sell.account"
        )
        db_session.add(token)
        db_session.commit()
        
        response = client.get("/ebay/oauth/status")
        
        assert response.status_code == 200
        data = response.json()
        assert data["connected"] is True
        assert "expires_in" in data
    
    def test_oauth_status_expired(self, client, db_session):
        """Test OAuth status when token is expired."""
        # Create an expired token
        encryption = get_encryption()
        
        now = int(datetime.now().timestamp() * 1000)
        expires_at = now - (7200 * 1000)  # Expired 2 hours ago
        
        token = Token(
            provider="ebay",
            access_token=encryption.encrypt("test-access-token"),
            refresh_token=encryption.encrypt("test-refresh-token"),
            expires_at=expires_at,
            token_type="Bearer",
            scope="sell.inventory"
        )
        db_session.add(token)
        db_session.commit()
        
        response = client.get("/ebay/oauth/status")
        
        assert response.status_code == 200
        data = response.json()
        assert data["connected"] is False
        assert "error" in data


class TestOAuthTokenExchange:
    """Test OAuth token exchange."""
    
    @patch('routes.ebay_oauth.OAuthFlow')
    def test_exchange_code_success(self, mock_oauth_flow_class, client, db_session):
        """Test successful code exchange."""
        mock_oauth_flow = MagicMock()
        mock_result = {
            "ok": True,
            "token": MagicMock(),
            "expires_in": 7200
        }
        mock_result["token"].provider = "ebay"
        mock_result["token"].expires_at = int((datetime.now() + timedelta(hours=2)).timestamp() * 1000)
        mock_result["token"].token_type = "Bearer"
        mock_result["token"].scope = "sell.inventory"
        mock_result["token"].created_at = int(datetime.now().timestamp() * 1000)
        
        mock_oauth_flow.exchange_code_for_token.return_value = mock_result
        mock_oauth_flow_class.return_value = mock_oauth_flow
        
        response = client.post("/ebay/oauth/exchange", json={"code": "test-auth-code"})
        
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
    
    @patch('routes.ebay_oauth.OAuthFlow')
    def test_exchange_code_failure(self, mock_oauth_flow_class, client, db_session):
        """Test failed code exchange."""
        mock_oauth_flow = MagicMock()
        mock_result = {
            "ok": False,
            "error": "Invalid authorization code",
            "token": None,
            "expires_in": None
        }
        mock_oauth_flow.exchange_code_for_token.return_value = mock_result
        mock_oauth_flow_class.return_value = mock_oauth_flow
        
        response = client.post("/ebay/oauth/exchange", json={"code": "invalid-code"})
        
        assert response.status_code == 400


class TestOAuthTokenRefresh:
    """Test OAuth token refresh."""
    
    @patch('routes.ebay_oauth.OAuthFlow')
    def test_refresh_token_success(self, mock_oauth_flow_class, client, db_session):
        """Test successful token refresh."""
        # Create existing token
        encryption = get_encryption()
        token_store = TokenStore(db_session, encryption)
        
        token_store.save_token(
            provider="ebay",
            access_token="old-access-token",
            refresh_token="test-refresh-token",
            expires_in=7200,
            token_type="Bearer",
            scope="sell.inventory"
        )
        
        mock_oauth_flow = MagicMock()
        mock_result = {
            "ok": True,
            "token": MagicMock(),
            "expires_in": 7200
        }
        mock_result["token"].provider = "ebay"
        mock_result["token"].expires_at = int((datetime.now() + timedelta(hours=2)).timestamp() * 1000)
        mock_result["token"].token_type = "Bearer"
        mock_result["token"].scope = "sell.inventory"
        mock_result["token"].updated_at = int(datetime.now().timestamp() * 1000)
        
        mock_oauth_flow.refresh_token.return_value = mock_result
        mock_oauth_flow_class.return_value = mock_oauth_flow
        
        response = client.post("/ebay/oauth/refresh")
        
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
    
    def test_refresh_token_no_token(self, client, db_session):
        """Test token refresh when no token exists."""
        response = client.post("/ebay/oauth/refresh")
        
        assert response.status_code == 404


class TestTokenStore:
    """Test token store functionality."""
    
    def test_save_and_get_token(self, db_session):
        """Test saving and retrieving token."""
        encryption = get_encryption()
        token_store = TokenStore(db_session, encryption)
        
        # Save token
        token = token_store.save_token(
            provider="ebay",
            access_token="test-access-token",
            refresh_token="test-refresh-token",
            expires_in=7200,
            token_type="Bearer",
            scope="sell.inventory"
        )
        
        assert token is not None
        assert token.provider == "ebay"
        
        # Get token
        retrieved = token_store.get_token("ebay")
        assert retrieved is not None
        assert retrieved.access_token == "test-access-token"
        assert retrieved.refresh_token == "test-refresh-token"
    
    def test_token_expiration_check(self, db_session):
        """Test token expiration checking."""
        encryption = get_encryption()
        token_store = TokenStore(db_session, encryption)
        
        now = int(datetime.now().timestamp() * 1000)
        
        # Create valid token
        valid_token = token_store.save_token(
            provider="ebay",
            access_token="test-access",
            refresh_token="test-refresh",
            expires_in=7200  # 2 hours
        )
        
        assert token_store.is_expired(valid_token) is False
        
        # Create expired token
        expired_token = Token(
            provider="ebay",
            access_token=encryption.encrypt("test-access"),
            refresh_token=encryption.encrypt("test-refresh"),
            expires_at=now - (7200 * 1000),  # Expired 2 hours ago
            token_type="Bearer",
            scope="sell.inventory"
        )
        
        assert token_store.is_expired(expired_token) is True

