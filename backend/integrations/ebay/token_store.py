"""
Token Store - Secure token storage and retrieval with encryption at rest.

Uses Fernet symmetric encryption for token security.
"""

import os
import base64
import logging
from typing import Optional
from datetime import datetime
from sqlmodel import Session, select
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from models import Token

logger = logging.getLogger(__name__)


class TokenEncryption:
    """Handles encryption/decryption of tokens."""
    
    def __init__(self, encryption_key: Optional[str] = None):
        """
        Initialize encryption with key.
        
        Args:
            encryption_key: Base64-encoded Fernet key. If None, derives from password.
        """
        if encryption_key:
            self.key = base64.urlsafe_b64decode(encryption_key.encode())
            self.fernet = Fernet(base64.urlsafe_b64encode(self.key))
        else:
            # Derive key from environment or use default (not recommended for production)
            password = os.getenv("TOKEN_ENCRYPTION_PASSWORD", "default-encryption-password-change-me").encode()
            salt = b"ebay_token_salt"  # Fixed salt for deterministic key
            
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=salt,
                iterations=100000,
            )
            key = base64.urlsafe_b64encode(kdf.derive(password))
            self.fernet = Fernet(key)
    
    def encrypt(self, plaintext: str) -> str:
        """Encrypt a string."""
        if not plaintext:
            return ""
        return self.fernet.encrypt(plaintext.encode()).decode()
    
    def decrypt(self, ciphertext: str) -> str:
        """Decrypt a string."""
        if not ciphertext:
            return ""
        return self.fernet.decrypt(ciphertext.encode()).decode()


# Global encryption instance
_encryption: Optional[TokenEncryption] = None


def get_encryption() -> TokenEncryption:
    """Get global encryption instance."""
    global _encryption
    if _encryption is None:
        key = os.getenv("TOKEN_ENCRYPTION_KEY")
        _encryption = TokenEncryption(encryption_key=key)
    return _encryption


class TokenStore:
    """Token storage and retrieval operations."""
    
    def __init__(self, session: Session, encryption: TokenEncryption = None):
        """
        Initialize token store.
        
        Args:
            session: Database session
            encryption: Encryption instance (uses global if None)
        """
        self.session = session
        self.encryption = encryption or get_encryption()
    
    def get_token(self, provider: str = "ebay") -> Optional[Token]:
        """
        Get current token for provider.
        
        Args:
            provider: Token provider (default: "ebay")
            
        Returns:
            Token instance or None if not found
        """
        token = self.session.get(Token, provider)
        if not token:
            return None
        
        # Decrypt tokens
        try:
            # Check if tokens are empty
            if not token.access_token or not token.refresh_token:
                logger.error(f"Token for {provider} has empty access_token or refresh_token")
                return None
            
            # Try to decrypt access token
            try:
                token.access_token = self.encryption.decrypt(token.access_token)
            except Exception as e:
                # Check if token is already plaintext (stored before encryption was added)
                if not token.access_token.startswith('gAAAAAB'):
                    # Token appears to be plaintext, use as-is
                    logger.warning(f"Token for {provider} appears to be unencrypted (doesn't start with gAAAAAB), using as-is")
                else:
                    # Real decryption error - log full details
                    logger.error(
                        f"Failed to decrypt access token for {provider}: {type(e).__name__}: {str(e)}. "
                        f"Token length: {len(token.access_token)}, starts with: {token.access_token[:20]}...",
                        exc_info=True
                    )
                    return None
            
            # Try to decrypt refresh token
            try:
                token.refresh_token = self.encryption.decrypt(token.refresh_token)
            except Exception as e:
                # Check if token is already plaintext
                if not token.refresh_token.startswith('gAAAAAB'):
                    # Token appears to be plaintext, use as-is
                    logger.warning(f"Refresh token for {provider} appears to be unencrypted (doesn't start with gAAAAAB), using as-is")
                else:
                    # Real decryption error - log full details
                    logger.error(
                        f"Failed to decrypt refresh token for {provider}: {type(e).__name__}: {str(e)}. "
                        f"Token length: {len(token.refresh_token)}, starts with: {token.refresh_token[:20]}...",
                        exc_info=True
                    )
                    return None
        except Exception as e:
            logger.error(
                f"Unexpected error decrypting token for {provider}: {type(e).__name__}: {str(e)}",
                exc_info=True
            )
            return None
        
        return token
    
    def save_token(
        self,
        provider: str,
        access_token: str,
        refresh_token: str,
        expires_in: int,  # Seconds until expiration
        token_type: str = "Bearer",
        scope: Optional[str] = None
    ) -> Token:
        """
        Save or update token.
        
        Args:
            provider: Token provider (default: "ebay")
            access_token: OAuth access token
            refresh_token: OAuth refresh token
            expires_in: Seconds until expiration
            token_type: Token type (default: "Bearer")
            scope: OAuth scopes granted
            
        Returns:
            Saved Token instance
        """
        now = int(datetime.now().timestamp() * 1000)
        expires_at = now + (expires_in * 1000)  # Convert to milliseconds
        
        # Encrypt tokens
        encrypted_access = self.encryption.encrypt(access_token)
        encrypted_refresh = self.encryption.encrypt(refresh_token)
        
        # Get or create token
        token = self.session.get(Token, provider)
        
        if token:
            # Update existing
            token.access_token = encrypted_access
            token.refresh_token = encrypted_refresh
            token.expires_at = expires_at
            token.token_type = token_type
            token.scope = scope
            token.updated_at = now
        else:
            # Create new
            token = Token(
                provider=provider,
                access_token=encrypted_access,
                refresh_token=encrypted_refresh,
                expires_at=expires_at,
                token_type=token_type,
                scope=scope,
                created_at=now,
                updated_at=now
            )
            self.session.add(token)
        
        self.session.commit()
        self.session.refresh(token)
        
        logger.info(f"Saved token for {provider}, expires at {expires_at}")
        return token
    
    def save_manual_token(
        self,
        provider: str,
        access_token: str,
        expires_in: int = 31536000,  # Default 1 year for manual tokens
        token_type: str = "Bearer",
        scope: Optional[str] = None
    ) -> Token:
        """
        Save a manual token (typically from eBay Developer Console).
        
        Manual tokens don't have refresh tokens, so we use the access_token
        as the refresh_token (even though it won't work for refresh).
        
        Args:
            provider: Token provider (default: "ebay")
            access_token: OAuth access token
            expires_in: Seconds until expiration (default: 1 year for manual tokens)
            token_type: Token type (default: "Bearer")
            scope: OAuth scopes granted
            
        Returns:
            Saved Token instance
        """
        # For manual tokens, use access_token as refresh_token
        # (won't work for refresh, but satisfies schema)
        return self.save_token(
            provider=provider,
            access_token=access_token,
            refresh_token=access_token,  # Manual tokens don't have separate refresh token
            expires_in=expires_in,
            token_type=token_type,
            scope=scope
        )
    
    def is_expired(self, token: Token, buffer_seconds: int = 300) -> bool:
        """
        Check if token is expired.
        
        Args:
            token: Token instance
            buffer_seconds: Buffer before expiration (default: 5 minutes)
            
        Returns:
            True if token is expired or will expire within buffer
        """
        if not token:
            return True
        
        now = int(datetime.now().timestamp() * 1000)
        buffer_ms = buffer_seconds * 1000
        return now >= (token.expires_at - buffer_ms)
    
    def delete_token(self, provider: str = "ebay") -> bool:
        """
        Delete token for provider.
        
        Args:
            provider: Token provider
            
        Returns:
            True if deleted, False if not found
        """
        token = self.session.get(Token, provider)
        if token:
            self.session.delete(token)
            self.session.commit()
            logger.info(f"Deleted token for {provider}")
            return True
        return False
    
    def get_valid_token(self, provider: str = "ebay") -> Optional[Token]:
        """
        Get valid (non-expired) token.
        
        Args:
            provider: Token provider
            
        Returns:
            Token instance if valid, None otherwise
        """
        token = self.get_token(provider)
        if not token:
            return None
        
        if self.is_expired(token):
            logger.info(f"Token for {provider} is expired")
            return None
        
        return token

