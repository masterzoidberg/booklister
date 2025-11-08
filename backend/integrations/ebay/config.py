"""
eBay OAuth Configuration - Loads and validates eBay OAuth settings.
"""

import os
import logging
from typing import Literal
from settings import EBaySettings

logger = logging.getLogger(__name__)


class OAuthConfig:
    """eBay OAuth configuration with validation."""
    
    def __init__(self, settings: EBaySettings = None):
        """Initialize OAuth config from settings."""
        self.settings = settings or EBaySettings()
        self._validate()
    
    def _validate(self) -> None:
        """Validate required configuration."""
        if not self.settings.ebay_client_id:
            raise ValueError("EBAY_CLIENT_ID is required")
        if not self.settings.ebay_client_secret:
            raise ValueError("EBAY_CLIENT_SECRET is required")
        if self.settings.ebay_env not in ["production", "sandbox"]:
            raise ValueError(f"EBAY_ENV must be 'production' or 'sandbox', got: {self.settings.ebay_env}")
    
    @property
    def client_id(self) -> str:
        """OAuth client ID."""
        return self.settings.ebay_client_id
    
    @property
    def client_secret(self) -> str:
        """OAuth client secret."""
        return self.settings.ebay_client_secret
    
    @property
    def redirect_uri(self) -> str:
        """OAuth redirect URI."""
        return self.settings.ebay_redirect_uri
    
    @property
    def scopes(self) -> str:
        """OAuth scopes (space-separated)."""
        return self.settings.ebay_scopes
    
    @property
    def environment(self) -> Literal["production", "sandbox"]:
        """eBay environment."""
        return self.settings.ebay_env
    
    def get_oauth_base_url(self) -> str:
        """Get OAuth base URL for environment."""
        return self.settings.get_oauth_base_url()
    
    def get_api_base_url(self) -> str:
        """Get API base URL for environment."""
        return self.settings.get_api_base_url()
    
    def get_authorization_url(self, state: str = None) -> str:
        """
        Generate eBay OAuth authorization URL.
        
        Args:
            state: Optional state parameter for CSRF protection
            
        Returns:
            Complete authorization URL
        """
        from urllib.parse import urlencode
        
        base_url = self.get_oauth_base_url()
        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "scope": self.scopes
        }
        
        if state:
            params["state"] = state
        
        # Build URL with properly encoded query parameters
        query_string = urlencode(params)
        return f"{base_url}/oauth/authorize?{query_string}"


# Global config instance
_oauth_config: OAuthConfig = None


def get_oauth_config() -> OAuthConfig:
    """Get global OAuth config instance."""
    global _oauth_config
    if _oauth_config is None:
        _oauth_config = OAuthConfig()
    return _oauth_config

