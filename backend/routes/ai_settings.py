"""
AI Settings Routes - Endpoints for managing AI provider configuration.
"""

import logging
import os
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session
from typing import Optional
from pydantic import BaseModel

from db import get_session
from services.ai_settings import AISettingsService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ai/settings", tags=["ai-settings"])


class AISettingsResponse(BaseModel):
    """Response for AI settings."""
    provider: str
    openai_api_key: Optional[str] = None  # Redacted
    openrouter_api_key: Optional[str] = None  # Redacted
    gemini_api_key: Optional[str] = None  # Redacted
    openai_model: str
    openrouter_model: str
    gemini_model: str


class UpdateAISettingsRequest(BaseModel):
    """Request to update AI settings."""
    provider: Optional[str] = None
    openai_api_key: Optional[str] = None  # Full key (will be encrypted)
    openrouter_api_key: Optional[str] = None  # Full key (will be encrypted)
    gemini_api_key: Optional[str] = None  # Full key (will be encrypted)


class TestConnectionResponse(BaseModel):
    """Response for connection test."""
    success: bool
    provider: str
    message: str


@router.get("", response_model=AISettingsResponse)
async def get_ai_settings(session: Session = Depends(get_session)):
    """
    Get current AI settings.
    
    Returns provider and redacted API keys (last 4 characters only).
    """
    try:
        service = AISettingsService(session)
        settings = service.get_settings()

        return AISettingsResponse(
            provider=settings["provider"],
            openai_api_key=settings["openai_api_key"],
            openrouter_api_key=settings["openrouter_api_key"],
            gemini_api_key=settings.get("gemini_api_key"),
            openai_model=settings["openai_model"],
            openrouter_model=settings["openrouter_model"],
            gemini_model=settings.get("gemini_model", "gemini-2.0-flash-exp")
        )
    except Exception as e:
        logger.error(f"Failed to get AI settings: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get AI settings: {str(e)}")


@router.post("", response_model=AISettingsResponse)
async def update_ai_settings(
    request: UpdateAISettingsRequest,
    session: Session = Depends(get_session)
):
    """
    Update AI settings.
    
    Updates provider and/or API keys. Keys are encrypted before storage.
    """
    try:
        service = AISettingsService(session)
        
        # Validate provider if provided
        if request.provider:
            valid_providers = ["openai", "openrouter", "gemini", "mock"]
            if request.provider not in valid_providers:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid provider: {request.provider}. Must be one of: {', '.join(valid_providers)}"
                )
            
            # Check if 'mock' is allowed in current environment
            if request.provider == "mock":
                app_env = os.getenv("APP_ENV", "").lower()
                node_env = os.getenv("NODE_ENV", "").lower()
                is_production = app_env == "production" or node_env == "production"
                
                if is_production:
                    raise HTTPException(
                        status_code=400,
                        detail="Provider 'mock' is not allowed in production. Set APP_ENV or NODE_ENV to a non-production value."
                    )
        
        # Update settings
        settings = service.update_settings(
            provider=request.provider,
            openai_api_key=request.openai_api_key,
            openrouter_api_key=request.openrouter_api_key,
            gemini_api_key=request.gemini_api_key
        )

        return AISettingsResponse(
            provider=settings["provider"],
            openai_api_key=settings["openai_api_key"],
            openrouter_api_key=settings["openrouter_api_key"],
            gemini_api_key=settings.get("gemini_api_key"),
            openai_model=settings["openai_model"],
            openrouter_model=settings["openrouter_model"],
            gemini_model=settings.get("gemini_model", "gemini-2.0-flash-exp")
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update AI settings: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to update AI settings: {str(e)}")


@router.post("/test", response_model=TestConnectionResponse)
async def test_ai_connection(session: Session = Depends(get_session)):
    """
    Test connection to current AI provider.
    
    Makes a minimal API call to verify the API key is valid.
    """
    try:
        from services.ai_settings import AISettingsService
        from openai import OpenAI
        
        service = AISettingsService(session)
        provider = service.get_active_provider()
        api_key = service.get_active_api_key()
        
        if not api_key:
            return TestConnectionResponse(
                success=False,
                provider=provider,
                message=f"No API key configured for provider '{provider}'"
            )
        
        # Test connection based on provider
        if provider == "openai":
            try:
                client = OpenAI(api_key=api_key)
                # Make a minimal test call
                client.models.list()
                return TestConnectionResponse(
                    success=True,
                    provider=provider,
                    message="Successfully connected to OpenAI"
                )
            except Exception as e:
                return TestConnectionResponse(
                    success=False,
                    provider=provider,
                    message=f"OpenAI connection failed: {str(e)}"
                )
        elif provider == "openrouter":
            try:
                # OpenRouter uses OpenAI-compatible API
                client = OpenAI(
                    api_key=api_key,
                    base_url="https://openrouter.ai/api/v1"
                )
                client.models.list()
                return TestConnectionResponse(
                    success=True,
                    provider=provider,
                    message="Successfully connected to OpenRouter"
                )
            except Exception as e:
                return TestConnectionResponse(
                    success=False,
                    provider=provider,
                    message=f"OpenRouter connection failed: {str(e)}"
                )
        elif provider == "gemini":
            try:
                # Test Gemini API connection
                import google.generativeai as genai
                genai.configure(api_key=api_key)
                # Make a minimal test call - list models
                models = genai.list_models()
                # Just iterate to verify the API call works
                list(models)
                return TestConnectionResponse(
                    success=True,
                    provider=provider,
                    message="Successfully connected to Google Gemini"
                )
            except ImportError:
                return TestConnectionResponse(
                    success=False,
                    provider=provider,
                    message="Gemini SDK not installed. Install with: pip install google-generativeai"
                )
            except Exception as e:
                return TestConnectionResponse(
                    success=False,
                    provider=provider,
                    message=f"Gemini connection failed: {str(e)}"
                )
        else:
            return TestConnectionResponse(
                success=False,
                provider=provider,
                message=f"Unknown provider: {provider}"
            )
    except Exception as e:
        logger.error(f"Failed to test AI connection: {e}", exc_info=True)
        return TestConnectionResponse(
            success=False,
            provider="unknown",
            message=f"Connection test failed: {str(e)}"
        )

