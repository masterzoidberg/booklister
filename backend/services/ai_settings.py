"""
AI Settings Service - Manages AI provider configuration and API keys.

Supports secure storage of OpenAI and OpenRouter API keys with encryption.
"""

import logging
from typing import Optional, Dict, Any
from sqlmodel import Session, select
from cryptography.fernet import Fernet
import base64

from models import Setting
from integrations.ebay.token_store import get_encryption
from settings import ai_settings

logger = logging.getLogger(__name__)

SETTINGS_KEY_AI_PROVIDER = "ai_provider"
SETTINGS_KEY_OPENAI_KEY = "ai_openai_api_key"
SETTINGS_KEY_OPENROUTER_KEY = "ai_openrouter_api_key"
SETTINGS_KEY_GEMINI_KEY = "ai_gemini_api_key"


class AISettingsService:
    """Service for managing AI provider settings and API keys."""
    
    def __init__(self, session: Session):
        """
        Initialize AI settings service.
        
        Args:
            session: Database session
        """
        self.session = session
        self.encryption = get_encryption()
    
    def get_settings(self) -> Dict[str, Any]:
        """
        Get current AI settings (with redacted keys).

        Returns:
            Dict with provider and redacted keys
        """
        # Get from database first, fallback to global settings
        provider = str(ai_settings.ai_provider.value)
        openai_key = None
        openrouter_key = None
        gemini_key = None

        # Try to get from database
        provider_setting = self.session.get(Setting, SETTINGS_KEY_AI_PROVIDER)
        if provider_setting and provider_setting.value:
            provider = provider_setting.value.get("value", provider)

        openai_setting = self.session.get(Setting, SETTINGS_KEY_OPENAI_KEY)
        if openai_setting and openai_setting.value:
            encrypted_key = openai_setting.value.get("value")
            if encrypted_key:
                try:
                    openai_key = self.encryption.decrypt(encrypted_key)
                except Exception as e:
                    logger.error(f"Failed to decrypt OpenAI key: {e}")

        openrouter_setting = self.session.get(Setting, SETTINGS_KEY_OPENROUTER_KEY)
        if openrouter_setting and openrouter_setting.value:
            encrypted_key = openrouter_setting.value.get("value")
            if encrypted_key:
                try:
                    openrouter_key = self.encryption.decrypt(encrypted_key)
                except Exception as e:
                    logger.error(f"Failed to decrypt OpenRouter key: {e}")

        gemini_setting = self.session.get(Setting, SETTINGS_KEY_GEMINI_KEY)
        if gemini_setting and gemini_setting.value:
            encrypted_key = gemini_setting.value.get("value")
            if encrypted_key:
                try:
                    gemini_key = self.encryption.decrypt(encrypted_key)
                except Exception as e:
                    logger.error(f"Failed to decrypt Gemini key: {e}")

        # Fallback to environment if not in database
        if not openai_key:
            openai_key = ai_settings.openai_api_key
        if not openrouter_key:
            openrouter_key = ai_settings.openrouter_api_key
        if not gemini_key:
            gemini_key = getattr(ai_settings, 'gemini_api_key', None)

        return {
            "provider": provider,
            "openai_api_key": self._redact_key(openai_key),
            "openrouter_api_key": self._redact_key(openrouter_key),
            "gemini_api_key": self._redact_key(gemini_key),
            "openai_model": ai_settings.openai_model,
            "openrouter_model": ai_settings.openrouter_model,
            "gemini_model": getattr(ai_settings, 'gemini_model', 'gemini-2.0-flash-exp')
        }
    
    def update_settings(
        self,
        provider: Optional[str] = None,
        openai_api_key: Optional[str] = None,
        openrouter_api_key: Optional[str] = None,
        gemini_api_key: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Update AI settings in database.

        Args:
            provider: AI provider ("openai", "openrouter", "gemini", or "mock")
            openai_api_key: OpenAI API key (will be encrypted)
            openrouter_api_key: OpenRouter API key (will be encrypted)
            gemini_api_key: Gemini API key (will be encrypted)

        Returns:
            Updated settings dict (with redacted keys)
        """
        from datetime import datetime
        
        # Update provider if provided
        if provider:
            provider_setting = self.session.get(Setting, SETTINGS_KEY_AI_PROVIDER)
            if provider_setting:
                provider_setting.value = {"value": provider}
            else:
                provider_setting = Setting(
                    key=SETTINGS_KEY_AI_PROVIDER,
                    value={"value": provider}
                )
                self.session.add(provider_setting)
        
        # Update OpenAI key if provided
        if openai_api_key is not None:
            openai_setting = self.session.get(Setting, SETTINGS_KEY_OPENAI_KEY)
            if openai_api_key:
                # Encrypt and store
                encrypted_key = self.encryption.encrypt(openai_api_key)
                if openai_setting:
                    openai_setting.value = {"value": encrypted_key}
                else:
                    openai_setting = Setting(
                        key=SETTINGS_KEY_OPENAI_KEY,
                        value={"value": encrypted_key}
                    )
                    self.session.add(openai_setting)
            else:
                # Empty string means clear the key
                if openai_setting:
                    openai_setting.value = None
        
        # Update OpenRouter key if provided
        if openrouter_api_key is not None:
            openrouter_setting = self.session.get(Setting, SETTINGS_KEY_OPENROUTER_KEY)
            if openrouter_api_key:
                # Encrypt and store
                encrypted_key = self.encryption.encrypt(openrouter_api_key)
                if openrouter_setting:
                    openrouter_setting.value = {"value": encrypted_key}
                else:
                    openrouter_setting = Setting(
                        key=SETTINGS_KEY_OPENROUTER_KEY,
                        value={"value": encrypted_key}
                    )
                    self.session.add(openrouter_setting)
            else:
                # Empty string means clear the key
                if openrouter_setting:
                    openrouter_setting.value = None

        # Update Gemini key if provided
        if gemini_api_key is not None:
            gemini_setting = self.session.get(Setting, SETTINGS_KEY_GEMINI_KEY)
            if gemini_api_key:
                # Encrypt and store
                encrypted_key = self.encryption.encrypt(gemini_api_key)
                if gemini_setting:
                    gemini_setting.value = {"value": encrypted_key}
                else:
                    gemini_setting = Setting(
                        key=SETTINGS_KEY_GEMINI_KEY,
                        value={"value": encrypted_key}
                    )
                    self.session.add(gemini_setting)
            else:
                # Empty string means clear the key
                if gemini_setting:
                    gemini_setting.value = None

        self.session.commit()
        
        return self.get_settings()
    
    def get_active_api_key(self) -> Optional[str]:
        """
        Get active API key based on current provider setting.

        Returns:
            Decrypted API key for current provider, or None
        """
        settings = self._get_raw_settings()
        provider = settings.get("provider", str(ai_settings.ai_provider.value))

        if provider == "openai":
            return settings.get("openai_api_key") or ai_settings.openai_api_key
        elif provider == "openrouter":
            return settings.get("openrouter_api_key") or ai_settings.openrouter_api_key
        elif provider == "gemini":
            return settings.get("gemini_api_key") or getattr(ai_settings, 'gemini_api_key', None)

        return None
    
    def get_active_provider(self) -> str:
        """Get current AI provider."""
        provider_setting = self.session.get(Setting, SETTINGS_KEY_AI_PROVIDER)
        if provider_setting and provider_setting.value:
            return provider_setting.value.get("value", str(ai_settings.ai_provider.value))
        return str(ai_settings.ai_provider.value)
    
    def _get_raw_settings(self) -> Dict[str, Any]:
        """Get raw settings with decrypted keys (internal use only)."""
        provider = self.get_active_provider()
        openai_key = None
        openrouter_key = None
        gemini_key = None

        openai_setting = self.session.get(Setting, SETTINGS_KEY_OPENAI_KEY)
        if openai_setting and openai_setting.value:
            encrypted_key = openai_setting.value.get("value")
            if encrypted_key:
                try:
                    openai_key = self.encryption.decrypt(encrypted_key)
                except Exception as e:
                    logger.error(f"Failed to decrypt OpenAI key: {e}")

        openrouter_setting = self.session.get(Setting, SETTINGS_KEY_OPENROUTER_KEY)
        if openrouter_setting and openrouter_setting.value:
            encrypted_key = openrouter_setting.value.get("value")
            if encrypted_key:
                try:
                    openrouter_key = self.encryption.decrypt(encrypted_key)
                except Exception as e:
                    logger.error(f"Failed to decrypt OpenRouter key: {e}")

        gemini_setting = self.session.get(Setting, SETTINGS_KEY_GEMINI_KEY)
        if gemini_setting and gemini_setting.value:
            encrypted_key = gemini_setting.value.get("value")
            if encrypted_key:
                try:
                    gemini_key = self.encryption.decrypt(encrypted_key)
                except Exception as e:
                    logger.error(f"Failed to decrypt Gemini key: {e}")

        # Fallback to environment
        if not openai_key:
            openai_key = ai_settings.openai_api_key
        if not openrouter_key:
            openrouter_key = ai_settings.openrouter_api_key
        if not gemini_key:
            gemini_key = getattr(ai_settings, 'gemini_api_key', None)

        return {
            "provider": provider,
            "openai_api_key": openai_key,
            "openrouter_api_key": openrouter_key,
            "gemini_api_key": gemini_key
        }
    
    def _redact_key(self, key: Optional[str]) -> Optional[str]:
        """
        Redact API key for display (show last 4 characters only).
        
        Args:
            key: API key to redact
        
        Returns:
            Redacted key string or None
        """
        if not key:
            return None
        
        if len(key) <= 4:
            return "*" * len(key)
        
        return "*" * (len(key) - 4) + key[-4:]

