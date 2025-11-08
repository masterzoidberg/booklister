"""
eBay Application-Level Authentication - Client Credentials OAuth Flow

This module handles OAuth 2.0 Client Credentials flow for accessing eBay public APIs
that don't require user authorization (e.g., Taxonomy API).

Unlike the user OAuth flow (authorization_code grant), this uses client_credentials
grant which only requires app credentials and doesn't need user authorization.

Token Lifetime: 7200 seconds (2 hours)
"""

import base64
import logging
import time
from typing import Optional, Dict, Any
from dataclasses import dataclass
from datetime import datetime, timedelta
import requests

from .config import get_oauth_config, OAuthConfig

logger = logging.getLogger(__name__)


@dataclass
class AppToken:
    """Application-level access token."""
    access_token: str
    expires_at: int  # Unix timestamp in seconds
    token_type: str = "Bearer"
    scope: str = "https://api.ebay.com/oauth/api_scope"

    def is_expired(self, buffer_seconds: int = 300) -> bool:
        """
        Check if token is expired or will expire soon.

        Args:
            buffer_seconds: Safety buffer (default 5 minutes)

        Returns:
            True if expired or expiring within buffer period
        """
        return time.time() >= (self.expires_at - buffer_seconds)


class AppAuthService:
    """
    Service for managing application-level OAuth tokens (client credentials flow).

    This is a singleton service that caches tokens in memory.
    Tokens are automatically refreshed when expired.
    """

    def __init__(self, config: Optional[OAuthConfig] = None):
        """
        Initialize app auth service.

        Args:
            config: OAuth config (uses global if None)
        """
        self.config = config or get_oauth_config()
        self._cached_token: Optional[AppToken] = None

    def get_access_token(self) -> Optional[str]:
        """
        Get valid application-level access token.

        Automatically fetches new token if cached token is expired or missing.

        Returns:
            Access token string, or None if failed to obtain token
        """
        # Check if cached token is valid
        if self._cached_token and not self._cached_token.is_expired():
            logger.debug("Using cached application token")
            return self._cached_token.access_token

        # Token expired or missing - fetch new one
        logger.info("Fetching new application-level access token")
        token = self._fetch_token()
        if token:
            self._cached_token = token
            expires_in_minutes = (token.expires_at - time.time()) / 60
            logger.info(f"Successfully obtained application token (expires in {expires_in_minutes:.1f} minutes)")
            return token.access_token
        else:
            logger.error("Failed to obtain application token")
            return None

    def _fetch_token(self) -> Optional[AppToken]:
        """
        Fetch new application-level access token using client credentials flow.

        Returns:
            AppToken object or None if request failed
        """
        try:
            # OAuth token endpoint for client credentials
            # Note: Token endpoint uses API base, not OAuth base
            # Authorization URL: https://auth.ebay.com/oauth2/authorize
            # Token endpoint: https://api.ebay.com/identity/v1/oauth2/token
            api_base = self.config.get_api_base_url()
            oauth_url = f"{api_base}/identity/v1/oauth2/token"

            # Build Basic Auth header
            credentials = f"{self.config.client_id}:{self.config.client_secret}"
            encoded_credentials = base64.b64encode(credentials.encode()).decode()

            headers = {
                "Content-Type": "application/x-www-form-urlencoded",
                "Authorization": f"Basic {encoded_credentials}"
            }

            # Client credentials grant
            data = {
                "grant_type": "client_credentials",
                "scope": "https://api.ebay.com/oauth/api_scope"
            }

            logger.debug(f"POST {oauth_url} (grant_type=client_credentials)")

            response = requests.post(
                oauth_url,
                headers=headers,
                data=data,
                timeout=30
            )

            if response.status_code == 200:
                token_data = response.json()

                # Parse response
                access_token = token_data.get("access_token")
                expires_in = token_data.get("expires_in", 7200)  # Default 2 hours
                token_type = token_data.get("token_type", "Bearer")

                if not access_token:
                    logger.error("No access_token in response")
                    return None

                # Calculate expiration timestamp
                expires_at = int(time.time() + expires_in)

                return AppToken(
                    access_token=access_token,
                    expires_at=expires_at,
                    token_type=token_type,
                    scope="https://api.ebay.com/oauth/api_scope"
                )
            else:
                error_data = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
                error_msg = error_data.get("error_description") or error_data.get("error") or response.text
                logger.error(f"Token request failed: {response.status_code} - {error_msg}")
                return None

        except requests.RequestException as e:
            logger.error(f"Network error during token request: {e}", exc_info=True)
            return None
        except Exception as e:
            logger.error(f"Unexpected error during token request: {e}", exc_info=True)
            return None

    def clear_cache(self):
        """Clear cached token (useful for testing)."""
        self._cached_token = None
        logger.debug("Cleared cached application token")


# Global singleton instance
_app_auth_service: Optional[AppAuthService] = None


def get_app_auth_service() -> AppAuthService:
    """
    Get global AppAuthService instance (singleton).

    Returns:
        AppAuthService instance
    """
    global _app_auth_service
    if _app_auth_service is None:
        _app_auth_service = AppAuthService()
    return _app_auth_service


def get_app_access_token() -> Optional[str]:
    """
    Convenience function to get application-level access token.

    Returns:
        Access token string or None if failed
    """
    service = get_app_auth_service()
    return service.get_access_token()
