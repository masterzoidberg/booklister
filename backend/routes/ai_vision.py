"""
AI Vision Routes - GPT-4o multimodal extraction endpoints.
"""

import logging
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session
from typing import Optional

from models import Book, BookStatus, ConditionGrade
from services.vision_extraction import VisionExtractionService
from db import get_session
from datetime import datetime

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ai/vision", tags=["ai-vision"])


@router.post("/{book_id}")
async def extract_book_vision(
    book_id: str,
    category_id: Optional[str] = Query(None, description="Optional eBay leaf category ID to filter extracted fields"),
    session: Session = Depends(get_session)
):
    """
    Extract structured book metadata from images using GPT-4o Vision API.

    This endpoint analyzes all images for a book and extracts metadata in a single call,
    replacing the OCR + metadata enrichment workflow.

    Args:
        book_id: The book ID to extract
        category_id: Optional eBay leaf category ID to filter extracted fields

    Supports both OpenAI and OpenRouter providers (configured via /ai/settings).

    Returns extracted fields mapped to Book model.
    """
    # Get the book
    book = session.get(Book, book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    try:
        # Create vision service with session to load settings from database
        vision_service = VisionExtractionService(session=session)

        # Perform vision extraction with category context
        result = await vision_service.extract_from_images_vision(book_id, category_id=category_id)
        
        if not result.get("ok", False):
            # Update book with errors for audit
            errors = result.get("errors", [])
            book.ai_validation_errors = errors  # Python list, not string
            book.updated_at = int(datetime.now().timestamp() * 1000)
            
            try:
                session.add(book)
                session.commit()
                session.refresh(book)
            except Exception as e:
                session.rollback()
                logger.error(f"Failed to save errors for book {book_id}: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to save errors: {str(e)}")
            
            # Return 200 with errors payload - UI will show toast
            return {
                "book_id": book_id,
                "ok": False,
                "errors": errors,
                "applied": False,
                "data": None,
                "status": book.status.value if hasattr(book.status, 'value') else book.status
            }
        
        # Map extracted fields to Book model
        mapped_fields = vision_service.map_to_book_fields(result.get("extracted", {}))

        # Validate critical fields - title must be present
        if not (mapped_fields.get("title_ai") or mapped_fields.get("title")):
            raise HTTPException(
                status_code=422,
                detail="Vision AI did not extract a title. Please ensure the book images clearly show the title page."
            )

        # Update book with extracted data
        for field, value in mapped_fields.items():
            if field == "condition_grade":
                # Handle ConditionGrade enum
                try:
                    book.condition_grade = ConditionGrade(value)
                except ValueError:
                    # Invalid condition, skip
                    continue
            else:
                setattr(book, field, value)
        
        # Ensure JSON fields are Python types, not strings
        book.ai_validation_errors = []  # Python list, not string '[]'
        if "specifics_ai" in mapped_fields:
            book.specifics_ai = mapped_fields["specifics_ai"]  # Python dict or None

        # Save category_id if provided
        if category_id:
            book.ebay_category_id = category_id
            logger.info(f"Saved category_id {category_id} to book {book_id}")

        # Update status
        if book.status == BookStatus.NEW:
            book.status = BookStatus.AUTO

        book.updated_at = int(datetime.now().timestamp() * 1000)
        
        try:
            session.add(book)
            session.commit()
            session.refresh(book)
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to save extracted data for book {book_id}: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to save extracted data: {str(e)}")
        
        return {
            "book_id": book_id,
            "ok": True,
            "errors": [],
            "applied": True,
            "data": result.get("extracted", {}),
            "extracted": result.get("extracted", {}),
            "mapped_fields": mapped_fields,
            "status": book.status.value if hasattr(book.status, 'value') else book.status
        }
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        logger.error(f"Error in vision extraction for book {book_id}: {e}", exc_info=True)
        # Handle unexpected errors gracefully
        error_message = f"Vision extraction error: {str(e)}"
        book.ai_validation_errors = [error_message]  # Python list
        book.updated_at = int(datetime.now().timestamp() * 1000)
        
        try:
            session.add(book)
            session.commit()
            session.refresh(book)
        except Exception as save_error:
            session.rollback()
            logger.error(f"Failed to save error state for book {book_id}: {save_error}")
            # Return error even if save failed
            return {
                "book_id": book_id,
                "ok": False,
                "errors": [error_message, f"Failed to save error state: {str(save_error)}"],
                "applied": False,
                "data": None,
                "status": book.status.value if hasattr(book.status, 'value') else book.status
            }
        
        # Return 200 with errors payload
        return {
            "book_id": book_id,
            "ok": False,
            "errors": [error_message],
            "applied": False,
            "data": None,
            "status": book.status.value if hasattr(book.status, 'value') else book.status
        }

