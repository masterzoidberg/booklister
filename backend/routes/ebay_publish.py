"""
eBay Publishing Routes - Endpoints for publishing books to eBay.
"""

import logging
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session
from typing import Optional
from pydantic import BaseModel

from db import get_session
from integrations.ebay.publish import publish_book
from models import Book

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ebay/publish", tags=["ebay-publish"])


class PublishRequest(BaseModel):
    """Request body for publishing."""
    payment_policy_id: Optional[str] = None
    return_policy_id: Optional[str] = None
    fulfillment_policy_id: Optional[str] = None
    category_id: Optional[str] = None
    as_draft: bool = False  # If True, creates offer but doesn't publish (saves as draft)


class PublishResponse(BaseModel):
    """Response for publish operation."""
    success: bool
    book_id: str
    sku: Optional[str] = None
    offer_id: Optional[str] = None
    listing_id: Optional[str] = None
    listing_url: Optional[str] = None
    steps: Optional[dict] = None
    error: Optional[str] = None


class PublishStatusResponse(BaseModel):
    """Response for publish status."""
    book_id: str
    sku: Optional[str] = None
    offer_id: Optional[str] = None
    listing_id: Optional[str] = None
    listing_url: Optional[str] = None
    publish_status: Optional[str] = None


@router.post("/{book_id}", response_model=PublishResponse)
async def publish_book_endpoint(
    book_id: str,
    request: Optional[PublishRequest] = None,
    session: Session = Depends(get_session)
):
    """
    Publish a book to eBay or save as draft.

    This endpoint:
    1. Creates or replaces inventory item
    2. Creates offer
    3. Publishes offer to create listing (unless as_draft=True)

    Set as_draft=True to create the offer without publishing (saves as draft).
    Policy IDs can be provided in request body or will be loaded from settings.
    """
    try:
        # Get book to verify it exists
        book = session.get(Book, book_id)
        if not book:
            raise HTTPException(status_code=404, detail=f"Book {book_id} not found")
        
        # Extract policy IDs and as_draft from request or use defaults
        payment_policy_id = request.payment_policy_id if request else None
        return_policy_id = request.return_policy_id if request else None
        fulfillment_policy_id = request.fulfillment_policy_id if request else None
        category_id = request.category_id if request else None
        as_draft = request.as_draft if request else False

        # Publish book (or save as draft)
        result = await publish_book(
            book_id=book_id,
            session=session,
            payment_policy_id=payment_policy_id,
            return_policy_id=return_policy_id,
            fulfillment_policy_id=fulfillment_policy_id,
            category_id=category_id,
            as_draft=as_draft
        )
        
        # Build response
        response = PublishResponse(
            success=result["success"],
            book_id=book_id,
            sku=result.get("sku"),
            offer_id=result.get("offer_id"),
            listing_id=result.get("listing_id"),
            listing_url=result.get("listing_url"),
            steps=result.get("steps"),
            error=result.get("error")
        )
        
        if not result["success"]:
            raise HTTPException(
                status_code=400,
                detail=result.get("error", "Publish failed")
            )
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to publish book {book_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to publish book: {str(e)}")


@router.get("/{book_id}/status", response_model=PublishStatusResponse)
async def get_publish_status(
    book_id: str,
    session: Session = Depends(get_session)
):
    """
    Get publish status for a book.
    
    Returns current publish status including SKU, offer ID, listing ID, and listing URL.
    """
    try:
        book = session.get(Book, book_id)
        if not book:
            raise HTTPException(status_code=404, detail=f"Book {book_id} not found")
        
        # Build listing URL if listing_id exists
        listing_url = None
        if book.ebay_listing_id:
            from settings import ebay_settings
            if ebay_settings.ebay_env == "sandbox":
                listing_url = f"https://sandbox.ebay.com/itm/{book.ebay_listing_id}"
            else:
                listing_url = f"https://www.ebay.com/itm/{book.ebay_listing_id}"
        
        return PublishStatusResponse(
            book_id=book_id,
            sku=book.sku,
            offer_id=book.ebay_offer_id,
            listing_id=book.ebay_listing_id,
            listing_url=listing_url,
            publish_status=book.publish_status
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get publish status for book {book_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get publish status: {str(e)}")

