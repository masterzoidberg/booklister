"""
eBay OAuth Flow - Handles authorization URL generation, code exchange, and token refresh.
"""

import logging
import requests
from typing import Dict, Any, Optional
from sqlmodel import Session

from .config import get_oauth_config, OAuthConfig
from .token_store import TokenStore, get_encryption

logger = logging.getLogger(__name__)


class OAuthError(Exception):
    """OAuth-related error."""
    pass


class OAuthFlow:
    """Handles eBay OAuth flow."""
    
    def __init__(self, config: OAuthConfig = None, session: Session = None):
        """
        Initialize OAuth flow.
        
        Args:
            config: OAuth config (uses global if None)
            session: Database session (required for token operations)
        """
        self.config = config or get_oauth_config()
        self.session = session
        if session:
            encryption = get_encryption()
            self.token_store = TokenStore(session, encryption)
        else:
            self.token_store = None
    
    def get_authorization_url(self, state: Optional[str] = None) -> str:
        """
        Generate eBay OAuth authorization URL.
        
        Args:
            state: Optional state parameter for CSRF protection
            
        Returns:
            Complete authorization URL
        """
        return self.config.get_authorization_url(state=state)
    
    def exchange_code_for_token(
        self,
        code: str,
        session: Session = None
    ) -> Dict[str, Any]:
        """
        Exchange authorization code for access token.
        
        Args:
            code: Authorization code from OAuth redirect
            session: Database session (required if not provided in constructor)
            
        Returns:
            Dict with token information:
            {
                "ok": bool,
                "error": str | None,
                "token": Token | None,
                "expires_in": int | None
            }
        """
        if session:
            encryption = get_encryption()
            token_store = TokenStore(session, encryption)
        elif self.token_store:
            token_store = self.token_store
        else:
            raise ValueError("Database session required for token exchange")
        
        try:
            # Prepare token exchange request
            oauth_url = f"{self.config.get_oauth_base_url()}/oauth/token"
            
            # eBay requires Basic Auth with client_id:client_secret
            import base64
            credentials = f"{self.config.client_id}:{self.config.client_secret}"
            encoded_credentials = base64.b64encode(credentials.encode()).decode()
            
            headers = {
                "Content-Type": "application/x-www-form-urlencoded",
                "Authorization": f"Basic {encoded_credentials}"
            }
            
            data = {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": self.config.redirect_uri
            }
            
            # Make token exchange request
            logger.info(f"Exchanging code for token with eBay OAuth")
            response = requests.post(oauth_url, headers=headers, data=data, timeout=30)
            
            if response.status_code != 200:
                error_msg = response.text
                logger.error(f"Token exchange failed: {response.status_code} - {error_msg}")
                return {
                    "ok": False,
                    "error": f"Token exchange failed: {response.status_code} - {error_msg}",
                    "token": None,
                    "expires_in": None
                }
            
            # Parse response
            token_data = response.json()
            
            access_token = token_data.get("access_token")
            refresh_token = token_data.get("refresh_token")
            expires_in = token_data.get("expires_in", 7200)  # Default 2 hours
            token_type = token_data.get("token_type", "Bearer")
            scope = token_data.get("scope")
            
            if not access_token or not refresh_token:
                error_msg = "Missing access_token or refresh_token in response"
                logger.error(f"Token exchange failed: {error_msg}")
                return {
                    "ok": False,
                    "error": error_msg,
                    "token": None,
                    "expires_in": None
                }
            
            # Save token to database
            token = token_store.save_token(
                provider="ebay",
                access_token=access_token,
                refresh_token=refresh_token,
                expires_in=expires_in,
                token_type=token_type,
                scope=scope
            )
            
            logger.info(f"Successfully exchanged code for token, expires in {expires_in}s")
            
            return {
                "ok": True,
                "error": None,
                "token": token,
                "expires_in": expires_in
            }
            
        except requests.RequestException as e:
            logger.error(f"Token exchange request failed: {e}")
            return {
                "ok": False,
                "error": f"Request failed: {str(e)}",
                "token": None,
                "expires_in": None
            }
        except Exception as e:
            logger.error(f"Token exchange error: {e}", exc_info=True)
            return {
                "ok": False,
                "error": f"Token exchange error: {str(e)}",
                "token": None,
                "expires_in": None
            }
    
    def refresh_token(
        self,
        refresh_token: str,
        session: Session = None
    ) -> Dict[str, Any]:
        """
        Refresh access token using refresh token.
        
        Args:
            refresh_token: Refresh token
            session: Database session (required if not provided in constructor)
            
        Returns:
            Dict with token information:
            {
                "ok": bool,
                "error": str | None,
                "token": Token | None,
                "expires_in": int | None
            }
        """
        if session:
            encryption = get_encryption()
            token_store = TokenStore(session, encryption)
        elif self.token_store:
            token_store = self.token_store
        else:
            raise ValueError("Database session required for token refresh")
        
        try:
            # Prepare refresh token request
            oauth_url = f"{self.config.get_oauth_base_url()}/oauth/token"
            
            # eBay requires Basic Auth with client_id:client_secret
            import base64
            credentials = f"{self.config.client_id}:{self.config.client_secret}"
            encoded_credentials = base64.b64encode(credentials.encode()).decode()
            
            headers = {
                "Content-Type": "application/x-www-form-urlencoded",
                "Authorization": f"Basic {encoded_credentials}"
            }
            
            data = {
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "scope": self.config.scopes
            }
            
            # Make refresh request
            logger.info(f"Refreshing token with eBay OAuth")
            response = requests.post(oauth_url, headers=headers, data=data, timeout=30)
            
            if response.status_code != 200:
                error_msg = response.text
                logger.error(f"Token refresh failed: {response.status_code} - {error_msg}")
                return {
                    "ok": False,
                    "error": f"Token refresh failed: {response.status_code} - {error_msg}",
                    "token": None,
                    "expires_in": None
                }
            
            # Parse response
            token_data = response.json()
            
            access_token = token_data.get("access_token")
            refresh_token_new = token_data.get("refresh_token", refresh_token)  # May not be returned
            expires_in = token_data.get("expires_in", 7200)  # Default 2 hours
            token_type = token_data.get("token_type", "Bearer")
            scope = token_data.get("scope", self.config.scopes)
            
            if not access_token:
                error_msg = "Missing access_token in refresh response"
                logger.error(f"Token refresh failed: {error_msg}")
                return {
                    "ok": False,
                    "error": error_msg,
                    "token": None,
                    "expires_in": None
                }
            
            # Save token to database
            token = token_store.save_token(
                provider="ebay",
                access_token=access_token,
                refresh_token=refresh_token_new,
                expires_in=expires_in,
                token_type=token_type,
                scope=scope
            )
            
            logger.info(f"Successfully refreshed token, expires in {expires_in}s")
            
            return {
                "ok": True,
                "error": None,
                "token": token,
                "expires_in": expires_in
            }
            
        except requests.RequestException as e:
            logger.error(f"Token refresh request failed: {e}")
            return {
                "ok": False,
                "error": f"Request failed: {str(e)}",
                "token": None,
                "expires_in": None
            }
        except Exception as e:
            logger.error(f"Token refresh error: {e}", exc_info=True)
            return {
                "ok": False,
                "error": f"Token refresh error: {str(e)}",
                "token": None,
                "expires_in": None
            }
    
    def get_valid_access_token(self, session: Session = None) -> Optional[str]:
        """
        Get valid access token, refreshing if needed.
        
        Args:
            session: Database session (required if not provided in constructor)
            
        Returns:
            Access token string or None if unavailable
        """
        if session:
            encryption = get_encryption()
            token_store = TokenStore(session, encryption)
        elif self.token_store:
            token_store = self.token_store
        else:
            raise ValueError("Database session required for token retrieval")
        
        # Get current token
        token = token_store.get_token("ebay")
        if not token:
            logger.warning("No token found for eBay")
            return None
        
        # Check if expired
        if token_store.is_expired(token):
            logger.info("Token expired, refreshing...")
            refresh_result = self.refresh_token(token.refresh_token, session)
            
            if refresh_result["ok"]:
                # Return new access token
                return refresh_result["token"].access_token
            else:
                logger.error(f"Token refresh failed: {refresh_result['error']}")
                return None
        
        # Token is valid
        return token.access_token

