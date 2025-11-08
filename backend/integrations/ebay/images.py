"""
Image URL resolver for eBay listings - Strategy B (Media API) or Strategy A (self-host)
"""
import os
import logging
from pathlib import Path
from typing import List, Optional
from sqlmodel import Session

from models import Book
from settings import ebay_settings
from integrations.ebay.media_api import upload_many, MediaAPIError, EbayMediaUploadError
from services.images.normalize import normalize_book_images
from services.filesystem import fs_service

logger = logging.getLogger(__name__)


async def resolve_listing_urls(
    book_id: str,
    token: str,
    session: Session,
    base_url: Optional[str] = None
) -> List[str]:
    """
    Resolve image URLs for eBay listing based on strategy.
    
    Strategy B (media): Upload images to eBay Picture Services, return EPS URLs.
    Strategy A (self_host): Return localhost/public URLs (requires tunnel/hosting).
    
    Args:
        book_id: Book ID
        token: OAuth bearer token
        session: Database session
        base_url: Base URL for self-host strategy (defaults from settings)
    
    Returns:
        List of HTTPS image URLs (EPS URLs for media strategy, public URLs for self-host)
    
    Raises:
        ValueError: If no images found, invalid count, or invalid URLs
        MediaAPIError: If Media API upload fails
    """
    # Get book with images
    book = session.get(Book, book_id)
    if not book:
        raise ValueError(f"Book not found: {book_id}")
    
    if not book.images:
        raise ValueError(f"Book {book_id} has no images")
    
    # Check image count limits
    max_images = ebay_settings.media_max_images
    if len(book.images) > max_images:
        logger.warning(
            f"Book {book_id} has {len(book.images)} images, limiting to {max_images}"
        )
        book.images = book.images[:max_images]
    
    if len(book.images) < 1:
        raise ValueError("At least 1 image required")
    
    # Route by strategy
    strategy = ebay_settings.image_strategy
    
    if strategy == "media":
        return await _resolve_media_urls(book_id, token, session, base_url)
    else:
        return _resolve_self_host_urls(book_id, base_url or "http://127.0.0.1:8000", session)


async def _resolve_media_urls(
    book_id: str,
    token: str,
    session: Session,
    base_url: Optional[str]
) -> List[str]:
    """
    Strategy B: Upload images to eBay Media API, return EPS URLs.
    
    Process:
    1. Gather normalized image paths for book
    2. Upload via Media API
    3. Validate EPS URLs (HTTPS, eBay domain)
    4. Return EPS URLs
    """
    # Get book
    book = session.get(Book, book_id)
    
    # Gather image paths
    base_dir = Path(ebay_settings.image_base_path)
    image_paths = []
    
    for img in book.images:
        # Extract filename from path
        path_str = img.path
        if '/' in path_str:
            filename = path_str.split('/')[-1]
        else:
            filename = path_str
        
        img_path = base_dir / book_id / filename
        
        if not img_path.exists():
            logger.warning(f"Image not found: {img_path}")
            continue
        
        image_paths.append(img_path)
    
    if not image_paths:
        raise ValueError(f"No valid image files found for book {book_id}")
    
    # Normalize images (resize, rotate EXIF, strip GPS, convert to JPEG)
    norm_dir = base_dir / book_id / "normalized"
    long_edge = ebay_settings.media_recommended_long_edge
    
    normalized_paths = normalize_book_images(
        book_id=book_id,
        image_paths=image_paths,
        base_dir=base_dir,
        long_edge=long_edge,
        quality=0.88
    )
    
    if not normalized_paths:
        raise ValueError(f"No normalized images created for book {book_id}")
    
    # Upload to Media API
    try:
        eps_urls = await upload_many(normalized_paths, token, base_url)
    except (MediaAPIError, EbayMediaUploadError) as e:
        request_id = getattr(e, 'request_id', None)
        status_code = getattr(e, 'status_code', None)
        logger.error(
            f"Media API upload failed for book {book_id}: {e}",
            extra={"request_id": request_id, "status_code": status_code}
        )
        raise ValueError(f"Image upload failed: {e}")
    
    # Validate EPS URLs
    _validate_eps_urls(eps_urls)
    
    return eps_urls


def _resolve_self_host_urls(
    book_id: str,
    base_url: str,
    session: Session
) -> List[str]:
    """
    Strategy A: Return self-hosted URLs (requires tunnel/hosting).
    
    Args:
        book_id: Book ID
        base_url: Base URL for images (must be HTTPS in production)
        session: Database session
    
    Returns:
        List of public image URLs
    
    Raises:
        ValueError: If URLs are invalid (not HTTPS)
    """
    book = session.get(Book, book_id)
    
    urls = []
    for img in book.images:
        path_str = img.path
        if '/' in path_str:
            filename = path_str.split('/')[-1]
        else:
            filename = path_str
        
        url = f"{base_url}/images/{book_id}/{filename}"
        urls.append(url)
    
    # Validate URLs are HTTPS (in production)
    if ebay_settings.ebay_env == "production":
        for url in urls:
            if not url.startswith('https://'):
                raise ValueError(
                    f"Production requires HTTPS URLs: {url}. "
                    "Use Strategy B (media) or set up HTTPS hosting."
                )
    
    return urls


def _validate_eps_urls(urls: List[str]) -> None:
    """
    Validate EPS URLs are HTTPS and point to eBay domains.
    
    Args:
        urls: List of URLs to validate
    
    Raises:
        ValueError: If any URL is invalid
    """
    ebay_domains = ['i.ebayimg.com', 'ebayimg.com']
    
    for url in urls:
        if not url.startswith('https://'):
            raise ValueError(f"EPS URL must be HTTPS: {url}")
        
        # Check if domain is eBay
        url_lower = url.lower()
        is_ebay = any(domain in url_lower for domain in ebay_domains)
        
        if not is_ebay:
            logger.warning(f"EPS URL does not match expected eBay domain: {url}")

