"""
eBay OAuth Routes - OAuth2 authentication endpoints.
"""

import logging
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session
from typing import Optional
from pydantic import BaseModel

from db import get_session
from integrations.ebay.oauth import OAuthFlow
from integrations.ebay.config import get_oauth_config
from integrations.ebay.token_store import TokenStore, get_encryption
from models import Token

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ebay/oauth", tags=["ebay-oauth"])


class ExchangeCodeRequest(BaseModel):
    """Request body for code exchange."""
    code: str


class SetManualTokenRequest(BaseModel):
    """Request body for manual token entry."""
    access_token: str
    expires_in: Optional[int] = None  # Optional, defaults to 1 year
    scope: Optional[str] = None


class OAuthStatusResponse(BaseModel):
    """OAuth status response."""
    connected: bool
    expires_at: Optional[int] = None
    expires_in: Optional[int] = None  # Seconds until expiration
    token_type: Optional[str] = None
    scope: Optional[str] = None
    error: Optional[str] = None


@router.get("/auth-url")
async def get_authorization_url(
    state: Optional[str] = Query(None, description="Optional state parameter for CSRF protection")
):
    """
    Get eBay OAuth authorization URL.
    
    User should visit this URL to authorize the application.
    After authorization, eBay redirects to redirect_uri with authorization code.
    """
    try:
        config = get_oauth_config()
        oauth_flow = OAuthFlow(config=config)
        
        auth_url = oauth_flow.get_authorization_url(state=state)
        
        return {
            "auth_url": auth_url,
            "redirect_uri": config.redirect_uri,
            "scopes": config.scopes
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to generate auth URL: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to generate authorization URL")


@router.post("/exchange")
async def exchange_code(
    request: ExchangeCodeRequest,
    session: Session = Depends(get_session)
):
    """
    Exchange authorization code for access token.
    
    After user authorizes at auth-url, eBay redirects with ?code=XXX.
    Extract the code and send it here to complete OAuth flow.
    """
    try:
        config = get_oauth_config()
        oauth_flow = OAuthFlow(config=config, session=session)
        
        result = oauth_flow.exchange_code_for_token(request.code, session)
        
        if not result["ok"]:
            raise HTTPException(
                status_code=400,
                detail=result.get("error", "Token exchange failed")
            )
        
        token = result["token"]
        
        return {
            "ok": True,
            "provider": token.provider,
            "expires_at": token.expires_at,
            "expires_in": result["expires_in"],
            "token_type": token.token_type,
            "scope": token.scope,
            "created_at": token.created_at
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to exchange code: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to exchange authorization code")


@router.post("/set-token")
async def set_manual_token(
    request: SetManualTokenRequest,
    session: Session = Depends(get_session)
):
    """
    Set a manual User Token from eBay Developer Console.
    
    This bypasses the OAuth flow. Use this if you have a User Token
    from the eBay Developer Console.
    
    Manual tokens are typically long-lived (don't expire quickly),
    so expiration is set to 1 year by default.
    """
    try:
        encryption = get_encryption()
        token_store = TokenStore(session, encryption)
        
        # Use default expiration of 1 year for manual tokens if not specified
        expires_in = request.expires_in if request.expires_in else 31536000  # 1 year
        
        # Save manual token
        token = token_store.save_manual_token(
            provider="ebay",
            access_token=request.access_token.strip(),
            expires_in=expires_in,
            scope=request.scope
        )
        
        logger.info(f"Saved manual token for eBay, expires at {token.expires_at}")
        
        return {
            "ok": True,
            "provider": token.provider,
            "expires_at": token.expires_at,
            "expires_in": expires_in,
            "token_type": token.token_type,
            "scope": token.scope,
            "created_at": token.created_at,
            "message": "Manual token saved successfully"
        }
    except Exception as e:
        logger.error(f"Failed to set manual token: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to save manual token: {str(e)}")


@router.get("/status", response_model=OAuthStatusResponse)
async def get_oauth_status(session: Session = Depends(get_session)):
    """
    Get current OAuth connection status.
    
    Returns whether valid tokens exist and when they expire.
    """
    try:
        encryption = get_encryption()
        token_store = TokenStore(session, encryption)
        
        token = token_store.get_token("ebay")
        
        if not token:
            return OAuthStatusResponse(
                connected=False,
                error="No token found. Please authorize via /ebay/oauth/auth-url"
            )
        
        # Check if expired
        is_expired = token_store.is_expired(token)
        
        if is_expired:
            return OAuthStatusResponse(
                connected=False,
                expires_at=token.expires_at,
                token_type=token.token_type,
                scope=token.scope,
                error="Token expired. Please refresh or re-authorize."
            )
        
        # Calculate seconds until expiration
        from datetime import datetime
        now = int(datetime.now().timestamp() * 1000)
        expires_in = max(0, (token.expires_at - now) // 1000)
        
        return OAuthStatusResponse(
            connected=True,
            expires_at=token.expires_at,
            expires_in=expires_in,
            token_type=token.token_type,
            scope=token.scope
        )
    except Exception as e:
        logger.error(f"Failed to get OAuth status: {e}", exc_info=True)
        return OAuthStatusResponse(
            connected=False,
            error=f"Failed to check status: {str(e)}"
        )


@router.post("/refresh")
async def refresh_token_endpoint(session: Session = Depends(get_session)):
    """
    Manually refresh the access token.
    
    Usually not needed - tokens are refreshed automatically when needed.
    """
    try:
        encryption = get_encryption()
        token_store = TokenStore(session, encryption)
        
        # Get current token
        token = token_store.get_token("ebay")
        if not token:
            raise HTTPException(
                status_code=404,
                detail="No token found. Please authorize via /ebay/oauth/auth-url"
            )
        
        # Refresh token
        config = get_oauth_config()
        oauth_flow = OAuthFlow(config=config, session=session)
        
        result = oauth_flow.refresh_token(token.refresh_token, session)
        
        if not result["ok"]:
            raise HTTPException(
                status_code=400,
                detail=result.get("error", "Token refresh failed")
            )
        
        refreshed_token = result["token"]
        
        return {
            "ok": True,
            "provider": refreshed_token.provider,
            "expires_at": refreshed_token.expires_at,
            "expires_in": result["expires_in"],
            "token_type": refreshed_token.token_type,
            "scope": refreshed_token.scope,
            "updated_at": refreshed_token.updated_at
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to refresh token: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to refresh token")


@router.delete("/disconnect")
async def disconnect_oauth(session: Session = Depends(get_session)):
    """
    Disconnect OAuth by deleting stored tokens.
    """
    try:
        encryption = get_encryption()
        token_store = TokenStore(session, encryption)
        
        deleted = token_store.delete_token("ebay")
        
        if deleted:
            return {"ok": True, "message": "OAuth disconnected successfully"}
        else:
            return {"ok": True, "message": "No token found to disconnect"}
    except Exception as e:
        logger.error(f"Failed to disconnect OAuth: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to disconnect OAuth")

