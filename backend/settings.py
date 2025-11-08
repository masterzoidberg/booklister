"""
Settings and configuration for eBay integration and AI providers
"""
import os
import logging
from enum import Enum
from typing import Literal, Optional
from pydantic import field_validator
from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)


class AIProvider(str, Enum):
    """AI provider options"""
    OPENAI = "openai"
    OPENROUTER = "openrouter"
    GEMINI = "gemini"
    MOCK = "mock"


class EBaySettings(BaseSettings):
    """eBay API configuration"""
    
    # Environment
    ebay_env: Literal["production", "sandbox"] = os.getenv("EBAY_ENV", "production")
    
    # Credentials
    ebay_client_id: str = os.getenv("EBAY_CLIENT_ID", "")
    ebay_client_secret: str = os.getenv("EBAY_CLIENT_SECRET", "")
    ebay_redirect_uri: str = os.getenv("EBAY_REDIRECT_URI", "http://localhost:3001/settings")
    ebay_scopes: str = os.getenv("EBAY_SCOPES", "sell.inventory sell.account sell.account.readonly")
    
    # Image Strategy
    image_strategy: Literal["media", "self_host"] = os.getenv("IMAGE_STRATEGY", "self_host")
    
    # Media API Settings
    media_max_images: int = int(os.getenv("MEDIA_MAX_IMAGES", "24"))
    media_min_long_edge: int = int(os.getenv("MEDIA_MIN_LONG_EDGE", "500"))
    media_recommended_long_edge: int = 1600
    ebay_marketplace_id: str = os.getenv("EBAY_MARKETPLACE_ID", "EBAY_US")
    ebay_media_base_url: Optional[str] = os.getenv("EBAY_MEDIA_BASE_URL", None)  # Optional override
    ebay_use_sandbox: bool = os.getenv("EBAY_USE_SANDBOX", "").lower() in ("true", "1", "yes")
    
    # Image Base Path
    image_base_path: str = os.getenv("IMAGE_BASE_PATH", "data/images")
    
    class Config:
        env_file = ".env"
        extra = "ignore"  # Ignore extra environment variables not defined in this class
    
    def get_api_base_url(self) -> str:
        """Get eBay API base URL based on environment"""
        if self.ebay_env == "sandbox":
            return "https://api.sandbox.ebay.com"
        return "https://api.ebay.com"
    
    def get_media_api_base_url(self) -> str:
        """Get eBay Media API base URL based on environment
        
        Note: Media API uses apim.ebay.com (different from main API)
        """
        if self.ebay_media_base_url:
            return self.ebay_media_base_url
        if self.ebay_env == "sandbox" or self.ebay_use_sandbox:
            return "https://apim.sandbox.ebay.com"
        return "https://apim.ebay.com"
    
    def get_oauth_base_url(self) -> str:
        """Get eBay OAuth base URL based on environment"""
        if self.ebay_env == "sandbox":
            return "https://auth.sandbox.ebay.com"
        return "https://auth.ebay.com"


class AISettings(BaseSettings):
    """AI provider configuration"""
    
    # Provider selection
    ai_provider: AIProvider = os.getenv("AI_PROVIDER", "openai")
    
    # API Keys (from environment, can be overridden from database)
    openai_api_key: Optional[str] = os.getenv("OPENAI_API_KEY", None)
    openrouter_api_key: Optional[str] = os.getenv("OPENROUTER_API_KEY", None)
    gemini_api_key: Optional[str] = os.getenv("GEMINI_API_KEY", None)

    # Model configuration
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4o")
    openrouter_model: str = os.getenv("OPENROUTER_MODEL", "openai/gpt-4o")
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-2.0-flash-exp")
    
    class Config:
        env_file = ".env"
        extra = "ignore"  # Ignore extra environment variables not defined in this class
    
    @field_validator("ai_provider", mode="after")
    @classmethod
    def validate_provider_in_production(cls, v: AIProvider) -> AIProvider:
        """Forbid 'mock' provider in production environment."""
        app_env = os.getenv("APP_ENV", "").lower()
        node_env = os.getenv("NODE_ENV", "").lower()
        
        is_production = app_env == "production" or node_env == "production"
        
        if is_production and v == AIProvider.MOCK:
            raise ValueError(
                "AI_PROVIDER='mock' is not allowed in production. "
                "Set APP_ENV or NODE_ENV to a non-production value, or use 'openai' or 'openrouter'."
            )
        return v
    
    def validate(self) -> None:
        """Validate settings and log warnings."""
        if self.ai_provider == AIProvider.OPENAI and not self.openai_api_key:
            logger.warning("AI_PROVIDER is set to 'openai' but OPENAI_API_KEY is not configured")
        elif self.ai_provider == AIProvider.OPENROUTER and not self.openrouter_api_key:
            logger.warning("AI_PROVIDER is set to 'openrouter' but OPENROUTER_API_KEY is not configured")
        elif self.ai_provider == AIProvider.GEMINI and not self.gemini_api_key:
            logger.warning("AI_PROVIDER is set to 'gemini' but GEMINI_API_KEY is not configured")


# Global settings instances
ebay_settings = EBaySettings()
ai_settings = AISettings()

# Validate AI settings on import
ai_settings.validate()

